-- Date dimension built from a spine (Kimball: a real calendar table, not on-the-fly
-- date functions). date_key is a YYYYMMDD integer used as the fact FK.
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
    extract(year    from date_day)::int       as year,
    extract(quarter from date_day)::int       as quarter,
    extract(month   from date_day)::int       as month,
    trim(to_char(date_day, 'Month'))          as month_name,
    extract(day     from date_day)::int       as day_of_month,
    extract(isodow  from date_day)::int       as day_of_week,
    (extract(isodow from date_day) in (6, 7)) as is_weekend
from spine
