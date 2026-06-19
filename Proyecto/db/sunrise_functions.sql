-- Función sunrise/sunset para Concepción, Chile
-- Coordenadas: -36.8201° S, -73.0455° W
-- Algoritmo: NOAA Solar Calculator (fórmula completa)
-- Timezone: Chile/Continental (UTC-4, sin horario de verano desde 2015)
-- Zenith: 90.833° (incluye refracción atmosférica)
--
-- Retorna timestamptz en UTC. Para convertir a hora local:
--   sunrise_concepcion(current_date) AT TIME ZONE 'Chile/Continental'

CREATE OR REPLACE FUNCTION sunrise_concepcion(dt date)
RETURNS timestamptz AS $$
DECLARE
    lat_rad double precision := radians(-36.8201);
    lng_deg double precision := -73.0455;

    n integer;
    gamma double precision;
    eq_time_min double precision;
    decl double precision;
    cos_ha double precision;
    ha_deg double precision;
    sunrise_min_utc double precision;
BEGIN
    n := extract(doy FROM dt)::integer;
    gamma := 2.0 * pi() / 365.0 * (n - 1);

    eq_time_min := 229.18 * (0.000075 + 0.001868 * cos(gamma)
                  - 0.032077 * sin(gamma) - 0.014615 * cos(2.0 * gamma)
                  - 0.040849 * sin(2.0 * gamma));

    decl := 0.006918 - 0.399912 * cos(gamma) + 0.070257 * sin(gamma)
            - 0.006758 * cos(2.0 * gamma) + 0.000907 * sin(2.0 * gamma)
            - 0.002697 * cos(3.0 * gamma) + 0.00148 * sin(3.0 * gamma);

    cos_ha := cos(radians(90.833)) / (cos(lat_rad) * cos(decl))
               - tan(lat_rad) * sin(decl) / (cos(lat_rad) * cos(decl));

    IF cos_ha < -1.0 THEN
        RETURN (dt::timestamp + interval '10 hours') AT TIME ZONE 'UTC';
    ELSIF cos_ha > 1.0 THEN
        RETURN (dt::timestamp + interval '16 hours') AT TIME ZONE 'UTC';
    END IF;

    ha_deg := degrees(acos(cos_ha));
    sunrise_min_utc := 720.0 - 4.0 * lng_deg - eq_time_min - 4.0 * ha_deg;

    -- Construir timestamp UTC directamente: date + minutes from midnight UTC
    RETURN (dt::timestamp + (sunrise_min_utc / 1440.0) * interval '1 day') AT TIME ZONE 'UTC';
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;


CREATE OR REPLACE FUNCTION sunset_concepcion(dt date)
RETURNS timestamptz AS $$
DECLARE
    lat_rad double precision := radians(-36.8201);
    lng_deg double precision := -73.0455;

    n integer;
    gamma double precision;
    eq_time_min double precision;
    decl double precision;
    cos_ha double precision;
    ha_deg double precision;
    sunset_min_utc double precision;
BEGIN
    n := extract(doy FROM dt)::integer;
    gamma := 2.0 * pi() / 365.0 * (n - 1);

    eq_time_min := 229.18 * (0.000075 + 0.001868 * cos(gamma)
                  - 0.032077 * sin(gamma) - 0.014615 * cos(2.0 * gamma)
                  - 0.040849 * sin(2.0 * gamma));

    decl := 0.006918 - 0.399912 * cos(gamma) + 0.070257 * sin(gamma)
            - 0.006758 * cos(2.0 * gamma) + 0.000907 * sin(2.0 * gamma)
            - 0.002697 * cos(3.0 * gamma) + 0.00148 * sin(3.0 * gamma);

    cos_ha := cos(radians(90.833)) / (cos(lat_rad) * cos(decl))
               - tan(lat_rad) * sin(decl) / (cos(lat_rad) * cos(decl));

    IF cos_ha < -1.0 OR cos_ha > 1.0 THEN
        RETURN (dt::timestamp + interval '22 hours') AT TIME ZONE 'UTC';
    END IF;

    ha_deg := degrees(acos(cos_ha));
    sunset_min_utc := 720.0 - 4.0 * lng_deg - eq_time_min + 4.0 * ha_deg;

    RETURN (dt::timestamp + (sunset_min_utc / 1440.0) * interval '1 day') AT TIME ZONE 'UTC';
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;