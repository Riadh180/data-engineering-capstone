-- Gold: occupation-level grain for correlations.
with unioned as (
    select 'general' as dataset, isco08_4digit, occupation_name,
           exposure_category, exposure_order,
           has_ai_usage::int as usage, has_ai_building::int as building, mean_task_score, match_method
    from {{ source('silver','jobs_kaggle') }}
    union all
    select 'tech', isco08_4digit, occupation_name, exposure_category, exposure_order,
           has_ai_usage::int, has_ai_building::int, mean_task_score, match_method
    from {{ source('silver','jobs_tech') }}
)
select dataset, isco08_4digit, occupation_name, exposure_category, exposure_order,
       count(*) as n_postings,
       round(avg(usage)::numeric,4) as ai_usage_rate,
       round(avg(building)::numeric,4) as ai_building_rate,
       round(avg(mean_task_score)::numeric,4) as mean_task_score
from unioned
where match_method <> 'unmapped'
group by 1,2,3,4,5
order by n_postings desc