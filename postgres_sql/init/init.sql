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