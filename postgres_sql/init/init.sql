CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    password VARCHAR(200) NOT NULL
);

INSERT INTO users (username, password)
VALUES ('m', 'pbkdf2:sha256:1000000$faDlBKlY2khSCuaY$a178f92924224403d54131dfb11837e07f273e3beadf2fa9b63d3430a09dcfbe');

CREATE TABLE available_bikes (
    id VARCHAR(50) PRIMARY KEY,
    minutes INTEGER NOT NULL,
    price INTEGER NOT NULL
);

CREATE TABLE stations_locations (
    station_id VARCHAR(50) PRIMARY KEY,
    lat_s NUMERIC(6,4) NOT NULL,
    lon_s NUMERIC(6,4) NOT NULL,
    address VARCHAR(200) NOT NULL,
    total_power INTEGER NOT NULL
);

CREATE TABLE rides (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    bike_id VARCHAR(50) NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active'
);