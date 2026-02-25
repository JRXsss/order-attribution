import os
import sys
import pymysql
import pandas as pd
from google.cloud import bigquery


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Missing env var: {name}")
    return v


def mysql_conn():
    return pymysql.connect(
        host=env("MYSQL_HOST"),
        user=env("MYSQL_USER"),
        password=env("MYSQL_PASSWORD"),
        database=env("MYSQL_DB"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def main():
    project_id = env("GCP_PROJECT_ID")
    bq_table = os.getenv(
        "BQ_TABLE",
        "project-fddee9ed-d147-4ffe-b75.From_mysql.shopline_order_statistics"
    )  # full: project.dataset.table
    mysql_table = env("MYSQL_TABLE")
    lookback_days = int(os.getenv("LOOKBACK_DAYS", "7"))

    bq = bigquery.Client(project=project_id)

    # 1) 取 MySQL 里“目前存在的日期集合”（建议只看最近 N 天，稳定&快）
    with mysql_conn() as conn:
        sql_dates = f"""
            SELECT DISTINCT DATE(date_time) AS dt
            FROM `{mysql_table}`
            WHERE date_time >= DATE_SUB(CURDATE(), INTERVAL {lookback_days} DAY)
              AND date_time IS NOT NULL
            ORDER BY dt
        """
        with conn.cursor() as cur:
            cur.execute(sql_dates)
            dates = [r["dt"] for r in cur.fetchall()]

        if not dates:
            print("No dates found in MySQL window; exit.")
            return

        print(f"Dates to refresh ({len(dates)}): {dates}")

        # 2) 删除 BQ 对应分区
        delete_sql = f"""
            DELETE FROM `{bq_table}`
            WHERE DATE(date_time) IN UNNEST(@dates)
        """
        delete_job = bq.query(
            delete_sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ArrayQueryParameter("dates", "DATE", dates)]
            ),
        )
        delete_job.result()
        print("Deleted partitions in BigQuery.")

        # 3) 按 dt 分批拉 MySQL + 写入 BQ（append）
        # 注意：字段顺序必须与你 BQ 表 schema 对齐
        select_cols = """
            id, order_seq, region, province, city, sales_channel, date_time,
            gross_sales, discounts, net_sales, tax, express_tax_amount,
            member_point_amount, shipping, tips, refunds, total_sales,
            order_quantity, return_quantity, adjust_amount, refund_adjust_amt
        """.strip()

        for dt in dates:
            extract_sql = f"""
                SELECT {select_cols}
                FROM `{mysql_table}`
                WHERE DATE(date_time) = %s
            """
            df = pd.read_sql(extract_sql, conn, params=[dt])

            if df.empty:
                print(f"{dt}: empty, skip.")
                continue

            # 强制类型（可选，但对稳定性很有帮助）
            # datetime -> datetime64, numeric -> float/Decimal 由 pandas/bq 自动处理
            df["date_time"] = pd.to_datetime(df["date_time"], errors="coerce")

            load_job = bq.load_table_from_dataframe(
                df,
                bq_table,
                job_config=bigquery.LoadJobConfig(
                    write_disposition=bigquery.WriteDisposition.WRITE_APPEND
                ),
            )
            load_job.result()
            print(f"{dt}: loaded {len(df)} rows.")

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
