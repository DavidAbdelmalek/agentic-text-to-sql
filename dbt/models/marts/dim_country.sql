-- Country dimension with a region rollup. Keeps a DACH angle on the real data: Germany,
-- Austria, Switzerland roll up to 'DACH'. CASE is ordered so DACH wins before 'Europe'.
with countries as (
    select distinct country from {{ ref('stg_online_retail') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['country']) }} as country_key,
    country,
    case
        when country in ('Germany', 'Austria', 'Switzerland') then 'DACH'
        when country in (
            'United Kingdom', 'EIRE', 'France', 'Netherlands', 'Belgium', 'Spain',
            'Portugal', 'Italy', 'Sweden', 'Denmark', 'Finland', 'Norway', 'Poland',
            'Channel Islands', 'Cyprus', 'Greece', 'Iceland', 'Lithuania', 'Malta',
            'Czech Republic', 'European Community'
        ) then 'Europe'
        else 'Rest of World'
    end as region
from countries
