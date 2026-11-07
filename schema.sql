CREATE TABLE states (
    state_code      CHAR(2) PRIMARY KEY,
    state_name      VARCHAR(50) NOT NULL,
    base_reg_fee    NUMERIC(8,2)
);

CREATE TABLE owners (
    owner_id        SERIAL PRIMARY KEY,
    first_name      VARCHAR(50),
    last_name       VARCHAR(50),
    address_line    VARCHAR(100),
    city            VARCHAR(50),
    state_code      CHAR(2),
    zip_code        VARCHAR(10)
);

CREATE TABLE vehicles (
    vehicle_id      SERIAL PRIMARY KEY,
    vin             VARCHAR(20),
    make            VARCHAR(30),
    model           VARCHAR(30),
    model_year      INTEGER,
    purchase_date   DATE,
    purchase_price  NUMERIC(10,2)
);

CREATE TABLE registrations (
    registration_id   SERIAL PRIMARY KEY,
    vehicle_id        INTEGER,
    owner_id          INTEGER,
    state_code        CHAR(2),
    plate_number      VARCHAR(10),
    issue_date        DATE,
    expiration_date   DATE,
    fee_paid          NUMERIC(8,2),
    status            VARCHAR(15)
);