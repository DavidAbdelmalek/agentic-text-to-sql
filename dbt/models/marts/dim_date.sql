-- Date dimension built from a spine (Kimball: a real calendar table). date_key is a
-- YYYYMMDD integer used as the fact FK. Snowflake date functions.
with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2009-12-01' as date)",
        end_date="cast('2012-01-01' as date)"
    ) }}
)

select
    to_char(date_day, 'YYYYMMDD')::int        as date_key,
    date_day::date                            as date,
    year(date_day)                            as year,
    quarter(date_day)                         as quarter,
    month(date_day)                           as month,
    to_char(date_day, 'MMMM')                 as month_name,
    day(date_day)                             as day_of_month,
    dayofweekiso(date_day)                    as day_of_week,
    (dayofweekiso(date_day) in (6, 7))        as is_weekend
from spine
