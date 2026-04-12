CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    password VARCHAR(200) NOT NULL
);

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
    start_lat NUMERIC(9,6),
    start_lon NUMERIC(9,6),
    end_lat NUMERIC(9,6),
    end_lon NUMERIC(9,6),
    start_battery FLOAT,
    status VARCHAR(20) DEFAULT 'active' -- 'active' o 'completed'
);