-- Gold: AI usage/building demand by dataset x exposure band x year.
-- Replaces src/gold/jobs_by_exposure.py (pandas groupby) with SQL.
with general as (
    select 'general' as dataset, exposure_order, exposure_category, year,
           has_ai_usage::int as usage, has_ai_building::int as building,
           mean_task_score, match_method
    from {{ source('silver','jobs_kaggle') }}
),
tech as (
    select 'tech' as dataset, exposure_order, exposure_category, year,
           has_ai_usage::int as usage, has_ai_building::int as building,
           mean_task_score, match_method
    from {{ source('silver','jobs_tech') }}
),
unioned as (select * from general union all select * from tech)
select
    dataset, exposure_order, exposure_category, year,
    count(*)                              as n_postings,
    round(avg(usage)::numeric, 4)         as ai_usage_rate,
    round(avg(building)::numeric, 4)      as ai_building_rate,
    round(avg(mean_task_score)::numeric,4) as avg_exposure
from unioned
where match_method <> 'unmapped'
group by 1,2,3,4
order by dataset, exposure_order desc, year