-- Sample legacy-shaped schema for local dev/testing.
-- Creates: a plain legacy table, a table with an enum-coded status column,
-- and a legacy retirement-reason table that encodes its reason as an enum code.

IF DB_ID('viewbuilder_legacy') IS NULL
BEGIN
    CREATE DATABASE viewbuilder_legacy;
END
GO

USE viewbuilder_legacy;
GO

IF OBJECT_ID('dbo.legacy_customer', 'U') IS NOT NULL DROP TABLE dbo.legacy_customer;
GO
CREATE TABLE dbo.legacy_customer (
    customer_id INT PRIMARY KEY,
    full_name NVARCHAR(200) NOT NULL,
    email NVARCHAR(200) NOT NULL,
    signup_date DATE NOT NULL
);
GO

INSERT INTO dbo.legacy_customer (customer_id, full_name, email, signup_date) VALUES
    (1, 'Ada Lovelace', 'ada@example.com', '2020-01-15'),
    (2, 'Grace Hopper', 'grace@example.com', '2020-03-22'),
    (3, 'Alan Turing', 'alan@example.com', '2021-06-01');
GO

-- Enum-coded status column: 1=Active, 2=Suspended, 3=Retired (see legacy_retirement_reason
-- for the enum meaning of the retirement-specific codes below).
IF OBJECT_ID('dbo.legacy_account', 'U') IS NOT NULL DROP TABLE dbo.legacy_account;
GO
CREATE TABLE dbo.legacy_account (
    account_id INT PRIMARY KEY,
    customer_id INT NOT NULL,
    status_code TINYINT NOT NULL,
    balance_cents INT NOT NULL
);
GO

INSERT INTO dbo.legacy_account (account_id, customer_id, status_code, balance_cents) VALUES
    (101, 1, 1, 15000),
    (102, 2, 1, 42000),
    (103, 3, 3, 0);
GO

-- Legacy retirement info, today encoded as enum codes:
-- reason_code: 1=UserRequested, 2=Fraud, 3=Inactivity, 4=Duplicate
IF OBJECT_ID('dbo.legacy_retirement_reason', 'U') IS NOT NULL DROP TABLE dbo.legacy_retirement_reason;
GO
CREATE TABLE dbo.legacy_retirement_reason (
    account_id INT PRIMARY KEY,
    reason_code TINYINT NOT NULL,
    retired_on DATE NOT NULL
);
GO

INSERT INTO dbo.legacy_retirement_reason (account_id, reason_code, retired_on) VALUES
    (103, 3, '2024-11-05');
GO

-- Target-side sample tables a mapping might write into.
IF OBJECT_ID('dbo.target_customer', 'U') IS NOT NULL DROP TABLE dbo.target_customer;
GO
CREATE TABLE dbo.target_customer (
    id INT PRIMARY KEY,
    display_name NVARCHAR(200) NOT NULL,
    email_address NVARCHAR(200) NOT NULL,
    created_at DATE NOT NULL
);
GO

IF OBJECT_ID('dbo.target_account', 'U') IS NOT NULL DROP TABLE dbo.target_account;
GO
CREATE TABLE dbo.target_account (
    id INT PRIMARY KEY,
    customer_id INT NOT NULL,
    status NVARCHAR(50) NOT NULL,
    balance_cents INT NOT NULL
);
GO

IF OBJECT_ID('dbo.retirement_audit', 'U') IS NOT NULL DROP TABLE dbo.retirement_audit;
GO
CREATE TABLE dbo.retirement_audit (
    audit_id INT IDENTITY(1,1) PRIMARY KEY,
    row_identity NVARCHAR(100) NOT NULL,
    retirement_reason NVARCHAR(100) NOT NULL,
    retired_at DATETIME2 NOT NULL,
    mapping_version NVARCHAR(100) NOT NULL
);
GO
