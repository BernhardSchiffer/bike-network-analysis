select ST_Distance(b."position", ST_GeomFromText(%s)) from Bikes_Tmp b 
where b.id = %s
and "time" < %s
order by "time" desc 
limit 1;