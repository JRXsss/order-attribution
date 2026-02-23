import os
import pymysql

DAYS = int(os.getenv("DAYS", "2"))
GROUP_CONCAT_MAX_LEN = int(os.getenv("GROUP_CONCAT_MAX_LEN", "1000000"))

SQL_SET = f"SET SESSION group_concat_max_len = {GROUP_CONCAT_MAX_LEN};"
SQL_DELETE = f"""
DELETE FROM caguuu_report.order_attribution
WHERE checkout_time >= DATE_SUB(CURDATE(), INTERVAL {DAYS} DAY);
"""

SQL_INSERT = f"""
INSERT INTO caguuu_report.order_attribution (
  order_seq, client_id, checkout_time,
  last_hit_event_time, last_hit_url, last_utm_source, last_utm_medium, last_utm_campaign, last_utm_content, last_utm_term,
  first_hit_event_time, first_hit_url, first_utm_source, first_utm_medium, first_utm_campaign, first_utm_content, first_utm_term
)
	SELECT
	    result.order_seq,
	    result.client_id,
	    result.checkout_time,
	
	    -- 最近一条有效 UTM（距离 checkout 最近）
	    result.last_hit_event_time,
	    result.last_hit_url,
	    result.last_utm_source,
	    result.last_utm_medium,
	    result.last_utm_campaign,
	    result.last_utm_content,
	    result.last_utm_term,
	
	    -- 最早一条有效 UTM（7天内最早）
	    result.first_hit_event_time,
	    result.first_hit_url,
	    result.first_utm_source,
	    result.first_utm_medium,
	    result.first_utm_campaign,
	    result.first_utm_content,
	    result.first_utm_term
	
	FROM (
	    SELECT
	        co.order_seq,
	        co.client_id,
	        co.checkout_time,
	
	        -- ===== 最近一条：ORDER BY event_time DESC =====
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.event_time ORDER BY eu.event_time DESC SEPARATOR '|||'),
	            '|||', 1
	        ) AS last_hit_event_time,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.page_url ORDER BY eu.event_time DESC SEPARATOR '|||'),
	            '|||', 1
	        ) AS last_hit_url,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_source ORDER BY eu.event_time DESC SEPARATOR '|||'),
	            '|||', 1
	        ) AS last_utm_source,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_medium ORDER BY eu.event_time DESC SEPARATOR '|||'),
	            '|||', 1
	        ) AS last_utm_medium,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_campaign ORDER BY eu.event_time DESC SEPARATOR '|||'),
	            '|||', 1
	        ) AS last_utm_campaign,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_content ORDER BY eu.event_time DESC SEPARATOR '|||'),
	            '|||', 1
	        ) AS last_utm_content,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_term ORDER BY eu.event_time DESC SEPARATOR '|||'),
	            '|||', 1
	        ) AS last_utm_term,
	
	        -- ===== 最早一条：ORDER BY event_time ASC =====
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.event_time ORDER BY eu.event_time ASC SEPARATOR '|||'),
	            '|||', 1
	        ) AS first_hit_event_time,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.page_url ORDER BY eu.event_time ASC SEPARATOR '|||'),
	            '|||', 1
	        ) AS first_hit_url,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_source ORDER BY eu.event_time ASC SEPARATOR '|||'),
	            '|||', 1
	        ) AS first_utm_source,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_medium ORDER BY eu.event_time ASC SEPARATOR '|||'),
	            '|||', 1
	        ) AS first_utm_medium,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_campaign ORDER BY eu.event_time ASC SEPARATOR '|||'),
	            '|||', 1
	        ) AS first_utm_campaign,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_content ORDER BY eu.event_time ASC SEPARATOR '|||'),
	            '|||', 1
	        ) AS first_utm_content,
	
	        SUBSTRING_INDEX(
	            GROUP_CONCAT(eu.utm_term ORDER BY eu.event_time ASC SEPARATOR '|||'),
	            '|||', 1
	        ) AS first_utm_term
	
	    FROM (
	        -- 子查询A：checkout_completed 事件
	        SELECT
	            client_id,
	            event_time AS checkout_time,
	            JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.orderSeq')) AS order_seq
	        FROM caguuu_erp.shopline_event_record_origin
	        WHERE event_name = 'checkout_completed'
	          AND JSON_EXTRACT(event_data, '$.orderSeq') IS NOT NULL
	          AND JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.orderSeq')) != ''
	           -- 只取近两天的 checkout 事件
              AND event_time >= DATE_SUB(CURDATE(), INTERVAL 2 DAY)
	    ) co
	    LEFT JOIN (
	        -- 子查询B：解析 event_data.url 中的 UTM 参数
	        SELECT
	            client_id,
	            event_time,
	            JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) AS page_url,
	
	            IF(
	                JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_source=%',
	                SUBSTRING_INDEX(
	                    SUBSTRING_INDEX(
	                        SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')), 'utm_source=', -1),
	                        '&', 1
	                    ), '#', 1
	                ),
	                NULL
	            ) AS utm_source,
	
	            IF(
	                JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_medium=%',
	                SUBSTRING_INDEX(
	                    SUBSTRING_INDEX(
	                        SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')), 'utm_medium=', -1),
	                        '&', 1
	                    ), '#', 1
	                ),
	                NULL
	            ) AS utm_medium,
	
	            IF(
	                JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_campaign=%',
	                SUBSTRING_INDEX(
	                    SUBSTRING_INDEX(
	                        SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')), 'utm_campaign=', -1),
	                        '&', 1
	                    ), '#', 1
	                ),
	                NULL
	            ) AS utm_campaign,
	
	            IF(
	                JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_content=%',
	                SUBSTRING_INDEX(
	                    SUBSTRING_INDEX(
	                        SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')), 'utm_content=', -1),
	                        '&', 1
	                    ), '#', 1
	                ),
	                NULL
	            ) AS utm_content,
	
	            IF(
	                JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_term=%',
	                SUBSTRING_INDEX(
	                    SUBSTRING_INDEX(
	                        SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')), 'utm_term=', -1),
	                        '&', 1
	                    ), '#', 1
	                ),
	                NULL
	            ) AS utm_term
	
	        FROM caguuu_erp.shopline_event_record_origin
	        WHERE JSON_EXTRACT(event_data, '$.url') IS NOT NULL
	          AND (
	                JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_source=%'
	             OR JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_medium=%'
	             OR JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_campaign=%'
	             OR JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_content=%'
	             OR JSON_UNQUOTE(JSON_EXTRACT(event_data, '$.url')) LIKE '%utm_term=%'
	          )
	           -- 回溯窗口最多往前9天（2天checkout + 7天回溯），减少扫描量
              AND event_time >= DATE_SUB(CURDATE(), INTERVAL 9 DAY)
	    ) eu
	      ON  eu.client_id  = co.client_id
	      AND eu.event_time <  co.checkout_time
	      AND eu.event_time >= DATE_SUB(co.checkout_time, INTERVAL 7 DAY)
	
	    GROUP BY co.order_seq, co.client_id, co.checkout_time
	
	) result
	ORDER BY result.checkout_time desc
	    ;
END
;
"""

def main():
    conn = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int((os.getenv("MYSQL_PORT") or "3306").strip()),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        db=os.environ.get("MYSQL_DB", "caguuu_report"),
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_SET)
            cur.execute(SQL_DELETE)
            cur.execute(SQL_INSERT)
        print("Done.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
