-- Banking-themed legacy schema for local dev/testing and the Portainer test deployment.
--
-- 5 legacy source tables (10-70 rows each), a shared enum-code lookup table (the
-- "current table that has that information as enums" pattern the whole project exists to
-- migrate away from), and a native SQL VIEW joining 3 of those tables together — this view
-- is a normal introspectable relation (see src/connectors/mssql.py::list_tables, which lists
-- views alongside tables) so it can be picked as a mapping source exactly like a table,
-- demonstrating a multi-table join feeding into the drag-and-drop mapping canvas.
--
-- Target-side sample tables + a retirement-audit table are also created, matching the shape
-- a mapping/retirement run would actually write into.

IF DB_ID('viewbuilder_legacy') IS NULL
BEGIN
    CREATE DATABASE viewbuilder_legacy;
END
GO

USE viewbuilder_legacy;
GO

-- ============================================================================
-- Drop everything up front, in reverse-dependency order, so this script is safely
-- re-runnable (e.g. on every redeploy) without FK-constraint drop failures partway
-- through — this MUST run before any CREATE TABLE below.
-- ============================================================================
IF OBJECT_ID('dbo.bank_customer_account_summary', 'V') IS NOT NULL DROP VIEW dbo.bank_customer_account_summary;
GO
IF OBJECT_ID('dbo.bank_account_closure_detail', 'V') IS NOT NULL DROP VIEW dbo.bank_account_closure_detail;
GO
IF OBJECT_ID('dbo.retirement_audit', 'U') IS NOT NULL DROP TABLE dbo.retirement_audit;
GO
IF OBJECT_ID('dbo.target_account', 'U') IS NOT NULL DROP TABLE dbo.target_account;
GO
IF OBJECT_ID('dbo.target_customer', 'U') IS NOT NULL DROP TABLE dbo.target_customer;
GO
IF OBJECT_ID('dbo.bank_account_closure', 'U') IS NOT NULL DROP TABLE dbo.bank_account_closure;
GO
IF OBJECT_ID('dbo.bank_transaction', 'U') IS NOT NULL DROP TABLE dbo.bank_transaction;
GO
IF OBJECT_ID('dbo.bank_card', 'U') IS NOT NULL DROP TABLE dbo.bank_card;
GO
IF OBJECT_ID('dbo.bank_account', 'U') IS NOT NULL DROP TABLE dbo.bank_account;
GO
IF OBJECT_ID('dbo.bank_customer', 'U') IS NOT NULL DROP TABLE dbo.bank_customer;
GO
IF OBJECT_ID('dbo.bank_branch', 'U') IS NOT NULL DROP TABLE dbo.bank_branch;
GO
IF OBJECT_ID('dbo.bank_enum_code', 'U') IS NOT NULL DROP TABLE dbo.bank_enum_code;
GO
-- Also drop the old (pre-banking-schema) sample tables from an earlier seed.sql version,
-- in case this is redeploying over a volume that still has them.
IF OBJECT_ID('dbo.legacy_customer', 'U') IS NOT NULL DROP TABLE dbo.legacy_customer;
GO
IF OBJECT_ID('dbo.legacy_retirement_reason', 'U') IS NOT NULL DROP TABLE dbo.legacy_retirement_reason;
GO
IF OBJECT_ID('dbo.legacy_account', 'U') IS NOT NULL DROP TABLE dbo.legacy_account;
GO

-- ============================================================================
-- 002-legacy-compat-view fixtures: an old wide table, its 5-table normalized
-- replacement, and a legacy XML document table. Dropped here (reverse-dependency
-- order) so this script stays safely re-runnable, matching the pattern above.
-- ============================================================================
IF OBJECT_ID('dbo.legacy_application_xml', 'U') IS NOT NULL DROP TABLE dbo.legacy_application_xml;
GO
IF OBJECT_ID('dbo.loan_document_ref', 'U') IS NOT NULL DROP TABLE dbo.loan_document_ref;
GO
IF OBJECT_ID('dbo.loan_underwriting', 'U') IS NOT NULL DROP TABLE dbo.loan_underwriting;
GO
IF OBJECT_ID('dbo.loan_collateral', 'U') IS NOT NULL DROP TABLE dbo.loan_collateral;
GO
IF OBJECT_ID('dbo.loan_applicant', 'U') IS NOT NULL DROP TABLE dbo.loan_applicant;
GO
IF OBJECT_ID('dbo.loan_application', 'U') IS NOT NULL DROP TABLE dbo.loan_application;
GO
IF OBJECT_ID('dbo.legacy_loan_application', 'U') IS NOT NULL DROP TABLE dbo.legacy_loan_application;
GO

-- ============================================================================
-- Shared enum-code lookup table: enum_id (the raw code business tables store),
-- name (the enum's category/domain), value (the human-readable meaning).
-- This is the "one big lookup table for many enum domains" pattern common in older
-- banking cores, where AccountStatus, TransactionType, CardStatus, ClosureReason etc.
-- all share one physical table keyed by a globally-unique surrogate id.
-- ============================================================================
IF OBJECT_ID('dbo.bank_enum_code', 'U') IS NOT NULL DROP TABLE dbo.bank_enum_code;
GO
CREATE TABLE dbo.bank_enum_code (
    enum_id INT PRIMARY KEY,
    name NVARCHAR(100) NOT NULL,
    value NVARCHAR(200) NOT NULL
);
GO

INSERT INTO dbo.bank_enum_code (enum_id, name, value) VALUES
    -- CustomerStatus (10-19)
    (10, 'CustomerStatus', 'Active'),
    (11, 'CustomerStatus', 'Dormant'),
    (12, 'CustomerStatus', 'Closed'),
    -- AccountStatus (20-29)
    (20, 'AccountStatus', 'Active'),
    (21, 'AccountStatus', 'Frozen'),
    (22, 'AccountStatus', 'Closed'),
    -- AccountType (30-39)
    (30, 'AccountType', 'Checking'),
    (31, 'AccountType', 'Savings'),
    (32, 'AccountType', 'MoneyMarket'),
    -- TransactionType (40-49)
    (40, 'TransactionType', 'Deposit'),
    (41, 'TransactionType', 'Withdrawal'),
    (42, 'TransactionType', 'Transfer'),
    (43, 'TransactionType', 'FeeAssessment'),
    (44, 'TransactionType', 'InterestPosting'),
    -- CardStatus (50-59)
    (50, 'CardStatus', 'Active'),
    (51, 'CardStatus', 'Blocked'),
    (52, 'CardStatus', 'Expired'),
    -- CardType (60-69)
    (60, 'CardType', 'Debit'),
    (61, 'CardType', 'Credit'),
    -- AccountClosureReason (70-79)
    (70, 'AccountClosureReason', 'CustomerRequested'),
    (71, 'AccountClosureReason', 'Fraud'),
    (72, 'AccountClosureReason', 'Inactivity'),
    (73, 'AccountClosureReason', 'Delinquency');
GO

-- ============================================================================
-- Table 1: branches (10 rows)
-- ============================================================================
IF OBJECT_ID('dbo.bank_branch', 'U') IS NOT NULL DROP TABLE dbo.bank_branch;
GO
CREATE TABLE dbo.bank_branch (
    branch_id INT PRIMARY KEY,
    branch_name NVARCHAR(150) NOT NULL,
    branch_city NVARCHAR(100) NOT NULL,
    opened_date DATE NOT NULL
);
GO

INSERT INTO dbo.bank_branch (branch_id, branch_name, branch_city, opened_date) VALUES
    (1, 'Downtown Main', 'Springfield', '1998-04-01'),
    (2, 'Riverside', 'Springfield', '2001-09-15'),
    (3, 'Northgate', 'Shelbyville', '2003-02-20'),
    (4, 'Capitol Square', 'Capital City', '2005-11-03'),
    (5, 'Ogdenville Crossing', 'Ogdenville', '2008-06-30'),
    (6, 'North Haverbrook', 'North Haverbrook', '2010-01-12'),
    (7, 'Brockway', 'Brockway', '2012-07-19'),
    (8, 'Old West Field', 'Old West Field', '2014-03-05'),
    (9, 'East Terminal', 'Springfield', '2017-10-22'),
    (10, 'Cypress Creek', 'Cypress Creek', '2020-05-08');
GO

-- ============================================================================
-- Table 2: customers (50 rows)
-- ============================================================================
IF OBJECT_ID('dbo.bank_customer', 'U') IS NOT NULL DROP TABLE dbo.bank_customer;
GO
CREATE TABLE dbo.bank_customer (
    customer_id INT PRIMARY KEY,
    full_name NVARCHAR(200) NOT NULL,
    email NVARCHAR(200) NOT NULL,
    branch_id INT NOT NULL REFERENCES dbo.bank_branch(branch_id),
    status_enum_id INT NOT NULL REFERENCES dbo.bank_enum_code(enum_id),
    signup_date DATE NOT NULL
);
GO

INSERT INTO dbo.bank_customer (customer_id, full_name, email, branch_id, status_enum_id, signup_date) VALUES
    (1, 'Ada Lovelace', 'ada.lovelace@example.com', 1, 10, '2015-01-15'),
    (2, 'Grace Hopper', 'grace.hopper@example.com', 1, 10, '2015-03-22'),
    (3, 'Alan Turing', 'alan.turing@example.com', 2, 10, '2016-06-01'),
    (4, 'Margaret Hamilton', 'margaret.hamilton@example.com', 2, 10, '2016-08-14'),
    (5, 'Katherine Johnson', 'katherine.johnson@example.com', 3, 10, '2016-11-02'),
    (6, 'Dorothy Vaughan', 'dorothy.vaughan@example.com', 3, 10, '2017-02-19'),
    (7, 'Mary Jackson', 'mary.jackson@example.com', 4, 10, '2017-05-30'),
    (8, 'Radia Perlman', 'radia.perlman@example.com', 4, 11, '2017-09-11'),
    (9, 'Barbara Liskov', 'barbara.liskov@example.com', 5, 10, '2018-01-07'),
    (10, 'Frances Allen', 'frances.allen@example.com', 5, 10, '2018-04-25'),
    (11, 'Shafi Goldwasser', 'shafi.goldwasser@example.com', 6, 10, '2018-07-13'),
    (12, 'Adele Goldberg', 'adele.goldberg@example.com', 6, 12, '2018-10-01'),
    (13, 'Jean Bartik', 'jean.bartik@example.com', 7, 10, '2019-01-18'),
    (14, 'Kathleen Booth', 'kathleen.booth@example.com', 7, 10, '2019-04-06'),
    (15, 'Lynn Conway', 'lynn.conway@example.com', 8, 10, '2019-07-24'),
    (16, 'Karen Sparck Jones', 'karen.sparckjones@example.com', 8, 11, '2019-11-11'),
    (17, 'Cynthia Breazeal', 'cynthia.breazeal@example.com', 9, 10, '2020-02-28'),
    (18, 'Fei-Fei Li', 'fei-fei.li@example.com', 9, 10, '2020-06-17'),
    (19, 'Anita Borg', 'anita.borg@example.com', 10, 10, '2020-10-04'),
    (20, 'Joan Clarke', 'joan.clarke@example.com', 1, 10, '2021-01-21'),
    (21, 'Hedy Lamarr', 'hedy.lamarr@example.com', 1, 10, '2021-05-10'),
    (22, 'Evelyn Boyd Granville', 'evelyn.granville@example.com', 2, 10, '2021-08-28'),
    (23, 'Annie Easley', 'annie.easley@example.com', 2, 10, '2021-12-15'),
    (24, 'Mary Wilkes', 'mary.wilkes@example.com', 3, 10, '2022-04-03'),
    (25, 'Erna Schneider Hoover', 'erna.hoover@example.com', 3, 10, '2022-07-21'),
    (26, 'Grace Murray', 'grace.murray@example.com', 4, 10, '2022-11-08'),
    (27, 'Susan Kare', 'susan.kare@example.com', 4, 10, '2023-02-25'),
    (28, 'Ruzena Bajcsy', 'ruzena.bajcsy@example.com', 5, 10, '2023-06-14'),
    (29, 'Wendy Hall', 'wendy.hall@example.com', 5, 10, '2023-10-01'),
    (30, 'Elizabeth Feinler', 'elizabeth.feinler@example.com', 6, 10, '2024-01-19'),
    (31, 'Carol Shaw', 'carol.shaw@example.com', 6, 10, '2024-05-07'),
    (32, 'Roberta Williams', 'roberta.williams@example.com', 7, 10, '2024-08-25'),
    (33, 'Brenda Laurel', 'brenda.laurel@example.com', 7, 10, '2024-12-12'),
    (34, 'Sophie Wilson', 'sophie.wilson@example.com', 8, 10, '2025-03-30'),
    (35, 'Jean Sammet', 'jean.sammet@example.com', 8, 10, '2025-07-17'),
    (36, 'Betty Holberton', 'betty.holberton@example.com', 9, 10, '2025-11-04'),
    (37, 'Ruth Teitelbaum', 'ruth.teitelbaum@example.com', 9, 10, '2018-02-14'),
    (38, 'Marlyn Meltzer', 'marlyn.meltzer@example.com', 10, 10, '2018-05-02'),
    (39, 'Frances Spence', 'frances.spence@example.com', 10, 10, '2018-08-20'),
    (40, 'Kathleen McNulty', 'kathleen.mcnulty@example.com', 1, 10, '2019-03-09'),
    (41, 'Klara von Neumann', 'klara.vonneumann@example.com', 2, 10, '2019-06-27'),
    (42, 'Ida Rhodes', 'ida.rhodes@example.com', 3, 10, '2019-10-14'),
    (43, 'Gertrude Blanch', 'gertrude.blanch@example.com', 4, 10, '2020-01-01'),
    (44, 'Mina Rees', 'mina.rees@example.com', 5, 10, '2020-04-19'),
    (45, 'Cecilia Payne-Gaposchkin', 'cecilia.payne@example.com', 6, 11, '2020-08-06'),
    (46, 'Vera Rubin', 'vera.rubin@example.com', 7, 10, '2020-11-24'),
    (47, 'Henrietta Leavitt', 'henrietta.leavitt@example.com', 8, 10, '2021-03-13'),
    (48, 'Annie Jump Cannon', 'annie.cannon@example.com', 9, 10, '2021-07-01'),
    (49, 'Williamina Fleming', 'williamina.fleming@example.com', 10, 10, '2021-10-19'),
    (50, 'Maria Mitchell', 'maria.mitchell@example.com', 1, 10, '2022-02-05');
GO

-- ============================================================================
-- Table 3: accounts (70 rows), split across customers above (1-3 accounts each)
-- ============================================================================
IF OBJECT_ID('dbo.bank_account', 'U') IS NOT NULL DROP TABLE dbo.bank_account;
GO
CREATE TABLE dbo.bank_account (
    account_id INT PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES dbo.bank_customer(customer_id),
    account_type_enum_id INT NOT NULL REFERENCES dbo.bank_enum_code(enum_id),
    status_enum_id INT NOT NULL REFERENCES dbo.bank_enum_code(enum_id),
    balance_cents BIGINT NOT NULL,
    opened_date DATE NOT NULL
);
GO

INSERT INTO dbo.bank_account (account_id, customer_id, account_type_enum_id, status_enum_id, balance_cents, opened_date) VALUES
    (1001, 1, 30, 20, 542311, '2015-01-16'),
    (1002, 1, 31, 20, 1200000, '2016-03-01'),
    (1003, 2, 30, 20, 88450, '2015-03-23'),
    (1004, 3, 30, 20, 234500, '2016-06-02'),
    (1005, 3, 32, 20, 5001200, '2018-09-10'),
    (1006, 4, 31, 20, 76300, '2016-08-15'),
    (1007, 5, 30, 20, 154200, '2016-11-03'),
    (1008, 6, 30, 21, 990, '2017-02-20'),
    (1009, 7, 31, 20, 442100, '2017-05-31'),
    (1010, 8, 30, 22, 0, '2017-09-12'),
    (1011, 9, 30, 20, 267800, '2018-01-08'),
    (1012, 9, 32, 20, 8123400, '2020-02-14'),
    (1013, 10, 31, 20, 315600, '2018-04-26'),
    (1014, 11, 30, 20, 92400, '2018-07-14'),
    (1015, 12, 30, 22, 0, '2018-10-02'),
    (1016, 13, 31, 20, 601200, '2019-01-19'),
    (1017, 14, 30, 20, 178900, '2019-04-07'),
    (1018, 15, 32, 20, 3005000, '2019-07-25'),
    (1019, 16, 30, 21, 4500, '2019-11-12'),
    (1020, 17, 30, 20, 233100, '2020-03-01'),
    (1021, 18, 31, 20, 812300, '2020-06-18'),
    (1022, 19, 30, 20, 45900, '2020-10-05'),
    (1023, 20, 30, 20, 621000, '2021-01-22'),
    (1024, 21, 32, 20, 9987600, '2021-05-11'),
    (1025, 22, 30, 20, 33200, '2021-08-29'),
    (1026, 23, 31, 20, 512400, '2021-12-16'),
    (1027, 24, 30, 20, 76100, '2022-04-04'),
    (1028, 25, 30, 20, 214700, '2022-07-22'),
    (1029, 26, 31, 20, 903000, '2022-11-09'),
    (1030, 27, 30, 20, 68500, '2023-02-26'),
    (1031, 28, 32, 20, 4213000, '2023-06-15'),
    (1032, 29, 30, 20, 129800, '2023-10-02'),
    (1033, 30, 31, 20, 55300, '2024-01-20'),
    (1034, 31, 30, 20, 891200, '2024-05-08'),
    (1035, 32, 30, 20, 302400, '2024-08-26'),
    (1036, 33, 31, 20, 45700, '2024-12-13'),
    (1037, 34, 30, 20, 128900, '2025-03-31'),
    (1038, 35, 32, 20, 6712000, '2025-07-18'),
    (1039, 36, 30, 20, 88200, '2025-11-05'),
    (1040, 37, 30, 20, 341000, '2018-02-15'),
    (1041, 38, 31, 20, 219500, '2018-05-03'),
    (1042, 39, 30, 20, 76800, '2018-08-21'),
    (1043, 40, 30, 20, 542000, '2019-03-10'),
    (1044, 41, 32, 20, 7300000, '2019-06-28'),
    (1045, 42, 30, 20, 91200, '2019-10-15'),
    (1046, 43, 31, 20, 405600, '2020-01-02'),
    (1047, 44, 30, 20, 133700, '2020-04-20'),
    (1048, 45, 30, 21, 2100, '2020-08-07'),
    (1049, 46, 32, 20, 5120000, '2020-11-25'),
    (1050, 47, 30, 20, 67400, '2021-03-14'),
    (1051, 48, 31, 20, 298700, '2021-07-02'),
    (1052, 49, 30, 20, 112300, '2021-10-20'),
    (1053, 50, 30, 20, 456700, '2022-02-06'),
    (1054, 2, 32, 20, 2011300, '2019-05-01'),
    (1055, 4, 30, 20, 88900, '2020-02-18'),
    (1056, 6, 31, 20, 341200, '2021-06-07'),
    (1057, 8, 32, 20, 998700, '2019-08-23'),
    (1058, 10, 30, 20, 55600, '2021-09-11'),
    (1059, 12, 31, 20, 123400, '2020-12-29'),
    (1060, 14, 30, 20, 789000, '2022-03-16'),
    (1061, 16, 32, 20, 3456000, '2021-04-02'),
    (1062, 18, 30, 20, 234100, '2022-06-20'),
    (1063, 20, 31, 20, 567800, '2023-01-07'),
    (1064, 22, 30, 20, 91100, '2023-04-25'),
    (1065, 24, 32, 20, 4567000, '2022-09-12'),
    (1066, 26, 30, 20, 65200, '2023-08-30'),
    (1067, 28, 31, 20, 345600, '2023-12-17'),
    (1068, 30, 30, 20, 178200, '2024-03-05'),
    (1069, 32, 32, 20, 6789000, '2024-06-23'),
    (1070, 34, 30, 20, 45300, '2024-10-10');
GO

-- ============================================================================
-- Table 4: cards (40 rows), split across accounts above
-- ============================================================================
IF OBJECT_ID('dbo.bank_card', 'U') IS NOT NULL DROP TABLE dbo.bank_card;
GO
CREATE TABLE dbo.bank_card (
    card_id INT PRIMARY KEY,
    account_id INT NOT NULL REFERENCES dbo.bank_account(account_id),
    card_type_enum_id INT NOT NULL REFERENCES dbo.bank_enum_code(enum_id),
    status_enum_id INT NOT NULL REFERENCES dbo.bank_enum_code(enum_id),
    issued_date DATE NOT NULL
);
GO

INSERT INTO dbo.bank_card (card_id, account_id, card_type_enum_id, status_enum_id, issued_date) VALUES
    (5001, 1001, 60, 50, '2015-01-20'),
    (5002, 1002, 61, 50, '2016-03-05'),
    (5003, 1003, 60, 50, '2015-03-27'),
    (5004, 1004, 60, 50, '2016-06-06'),
    (5005, 1005, 61, 50, '2018-09-14'),
    (5006, 1006, 60, 51, '2016-08-19'),
    (5007, 1007, 60, 50, '2016-11-07'),
    (5008, 1008, 60, 51, '2017-02-24'),
    (5009, 1009, 61, 50, '2017-06-04'),
    (5010, 1010, 60, 52, '2017-09-16'),
    (5011, 1011, 60, 50, '2018-01-12'),
    (5012, 1012, 61, 50, '2020-02-18'),
    (5013, 1013, 60, 50, '2018-04-30'),
    (5014, 1014, 60, 50, '2018-07-18'),
    (5015, 1016, 61, 50, '2019-01-23'),
    (5016, 1017, 60, 50, '2019-04-11'),
    (5017, 1018, 61, 50, '2019-07-29'),
    (5018, 1020, 60, 50, '2020-03-05'),
    (5019, 1021, 60, 50, '2020-06-22'),
    (5020, 1023, 60, 50, '2021-01-26'),
    (5021, 1024, 61, 50, '2021-05-15'),
    (5022, 1026, 60, 50, '2021-12-20'),
    (5023, 1028, 60, 50, '2022-07-26'),
    (5024, 1029, 61, 50, '2022-11-13'),
    (5025, 1031, 61, 50, '2023-06-19'),
    (5026, 1033, 60, 51, '2024-01-24'),
    (5027, 1034, 60, 50, '2024-05-12'),
    (5028, 1037, 60, 50, '2025-04-04'),
    (5029, 1038, 61, 50, '2025-07-22'),
    (5030, 1040, 60, 50, '2018-02-19'),
    (5031, 1041, 61, 50, '2018-05-07'),
    (5032, 1043, 60, 50, '2019-03-14'),
    (5033, 1044, 61, 50, '2019-07-02'),
    (5034, 1046, 60, 50, '2020-01-06'),
    (5035, 1049, 61, 50, '2020-11-29'),
    (5036, 1051, 60, 50, '2021-07-06'),
    (5037, 1053, 60, 50, '2022-02-10'),
    (5038, 1058, 60, 50, '2021-09-15'),
    (5039, 1063, 60, 50, '2023-01-11'),
    (5040, 1069, 61, 50, '2024-06-27');
GO

-- ============================================================================
-- Table 5: transactions (60 rows), split across accounts above
-- ============================================================================
IF OBJECT_ID('dbo.bank_transaction', 'U') IS NOT NULL DROP TABLE dbo.bank_transaction;
GO
CREATE TABLE dbo.bank_transaction (
    transaction_id INT PRIMARY KEY,
    account_id INT NOT NULL REFERENCES dbo.bank_account(account_id),
    transaction_type_enum_id INT NOT NULL REFERENCES dbo.bank_enum_code(enum_id),
    amount_cents BIGINT NOT NULL,
    transaction_date DATE NOT NULL
);
GO

INSERT INTO dbo.bank_transaction (transaction_id, account_id, transaction_type_enum_id, amount_cents, transaction_date) VALUES
    (9001, 1001, 40, 100000, '2026-01-02'),
    (9002, 1001, 41, -25000, '2026-01-05'),
    (9003, 1002, 40, 500000, '2026-01-03'),
    (9004, 1002, 44, 1200, '2026-01-31'),
    (9005, 1003, 41, -10000, '2026-01-06'),
    (9006, 1003, 40, 20000, '2026-01-10'),
    (9007, 1004, 42, -5000, '2026-01-08'),
    (9008, 1005, 40, 2000000, '2026-01-09'),
    (9009, 1005, 43, -500, '2026-01-15'),
    (9010, 1006, 41, -3000, '2026-01-11'),
    (9011, 1007, 40, 75000, '2026-01-12'),
    (9012, 1008, 41, -990, '2026-01-13'),
    (9013, 1009, 40, 150000, '2026-01-14'),
    (9014, 1011, 40, 60000, '2026-01-16'),
    (9015, 1012, 40, 3000000, '2026-01-17'),
    (9016, 1012, 44, 3200, '2026-01-31'),
    (9017, 1013, 42, -20000, '2026-01-18'),
    (9018, 1014, 40, 45000, '2026-01-19'),
    (9019, 1016, 40, 250000, '2026-01-20'),
    (9020, 1017, 41, -8000, '2026-01-21'),
    (9021, 1018, 40, 1000000, '2026-01-22'),
    (9022, 1020, 40, 90000, '2026-01-23'),
    (9023, 1021, 42, -30000, '2026-01-24'),
    (9024, 1023, 40, 120000, '2026-01-25'),
    (9025, 1024, 40, 4000000, '2026-01-26'),
    (9026, 1024, 44, 4500, '2026-01-31'),
    (9027, 1026, 41, -15000, '2026-01-27'),
    (9028, 1028, 40, 80000, '2026-01-28'),
    (9029, 1029, 42, -40000, '2026-01-29'),
    (9030, 1031, 40, 1500000, '2026-01-30'),
    (9031, 1033, 41, -6000, '2026-02-01'),
    (9032, 1034, 40, 200000, '2026-02-02'),
    (9033, 1035, 40, 95000, '2026-02-03'),
    (9034, 1037, 41, -4000, '2026-02-04'),
    (9035, 1038, 40, 2500000, '2026-02-05'),
    (9036, 1039, 40, 30000, '2026-02-06'),
    (9037, 1040, 42, -10000, '2026-02-07'),
    (9038, 1041, 40, 60000, '2026-02-08'),
    (9039, 1043, 40, 175000, '2026-02-09'),
    (9040, 1044, 40, 3000000, '2026-02-10'),
    (9041, 1046, 41, -12000, '2026-02-11'),
    (9042, 1047, 40, 42000, '2026-02-12'),
    (9043, 1049, 40, 2000000, '2026-02-13'),
    (9044, 1050, 41, -5000, '2026-02-14'),
    (9045, 1051, 40, 88000, '2026-02-15'),
    (9046, 1052, 40, 33000, '2026-02-16'),
    (9047, 1053, 42, -20000, '2026-02-17'),
    (9048, 1054, 40, 900000, '2026-02-18'),
    (9049, 1056, 40, 110000, '2026-02-19'),
    (9050, 1057, 40, 400000, '2026-02-20'),
    (9051, 1058, 41, -3000, '2026-02-21'),
    (9052, 1059, 40, 45000, '2026-02-22'),
    (9053, 1060, 40, 250000, '2026-02-23'),
    (9054, 1061, 44, 5600, '2026-02-28'),
    (9055, 1062, 40, 70000, '2026-02-24'),
    (9056, 1063, 42, -25000, '2026-02-25'),
    (9057, 1064, 40, 30000, '2026-02-26'),
    (9058, 1065, 40, 1800000, '2026-02-27'),
    (9059, 1066, 41, -2000, '2026-02-28'),
    (9060, 1070, 40, 15000, '2026-03-01');
GO

-- ============================================================================
-- Retirement source: accounts closed, reason stored as an enum code
-- (this is the "current table that has that information as enums" the retirement
-- feature (US3) migrates into an append-only audit record with a translated reason).
-- ============================================================================
IF OBJECT_ID('dbo.bank_account_closure', 'U') IS NOT NULL DROP TABLE dbo.bank_account_closure;
GO
CREATE TABLE dbo.bank_account_closure (
    account_id INT PRIMARY KEY REFERENCES dbo.bank_account(account_id),
    reason_enum_id INT NOT NULL REFERENCES dbo.bank_enum_code(enum_id),
    closed_on DATE NOT NULL
);
GO

INSERT INTO dbo.bank_account_closure (account_id, reason_enum_id, closed_on) VALUES
    (1010, 70, '2019-05-01'),
    (1015, 72, '2021-08-14'),
    (1019, 71, '2022-02-09');
GO

-- ============================================================================
-- A native SQL VIEW joining 3 of the tables above (customer + account + branch).
-- Introspected and selectable as a mapping source exactly like a table (see
-- src/connectors/mssql.py::list_tables) — lets the drag-and-drop canvas map columns
-- that actually came from a 3-table join, without the mapping engine needing to know
-- anything about joins itself.
-- ============================================================================
IF OBJECT_ID('dbo.bank_customer_account_summary', 'V') IS NOT NULL DROP VIEW dbo.bank_customer_account_summary;
GO
CREATE VIEW dbo.bank_customer_account_summary AS
SELECT
    a.account_id,
    c.customer_id,
    c.full_name,
    c.email,
    br.branch_id,
    br.branch_name,
    br.branch_city,
    a.account_type_enum_id,
    a.status_enum_id AS account_status_enum_id,
    a.balance_cents,
    a.opened_date AS account_opened_date
FROM dbo.bank_account a
JOIN dbo.bank_customer c ON c.customer_id = a.customer_id
JOIN dbo.bank_branch br ON br.branch_id = c.branch_id;
GO

-- ============================================================================
-- A second VIEW joining accounts to their closure record, giving the retirement
-- mapping (US3) a single source relation carrying both status_enum_id and
-- reason_enum_id together — the legacy tables split these across bank_account and
-- bank_account_closure, which is realistic (status lives on the account row, the
-- closure reason is a separate historical record) but the retirement engine reads
-- both from one source_table, so a view is exactly the right tool here too.
-- ============================================================================
IF OBJECT_ID('dbo.bank_account_closure_detail', 'V') IS NOT NULL DROP VIEW dbo.bank_account_closure_detail;
GO
CREATE VIEW dbo.bank_account_closure_detail AS
SELECT
    a.account_id,
    a.status_enum_id,
    cl.reason_enum_id,
    cl.closed_on
FROM dbo.bank_account a
JOIN dbo.bank_account_closure cl ON cl.account_id = a.account_id;
GO

-- ============================================================================
-- Target-side sample tables a mapping might write into.
-- ============================================================================
IF OBJECT_ID('dbo.target_customer', 'U') IS NOT NULL DROP TABLE dbo.target_customer;
GO
CREATE TABLE dbo.target_customer (
    id INT PRIMARY KEY,
    display_name NVARCHAR(200) NOT NULL,
    email_address NVARCHAR(200) NOT NULL,
    branch_name NVARCHAR(150) NULL,
    created_at DATE NOT NULL
);
GO

IF OBJECT_ID('dbo.target_account', 'U') IS NOT NULL DROP TABLE dbo.target_account;
GO
CREATE TABLE dbo.target_account (
    id INT PRIMARY KEY,
    customer_id INT NOT NULL,
    account_type NVARCHAR(50) NULL,
    status NVARCHAR(50) NOT NULL,
    balance_cents BIGINT NOT NULL
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

-- ============================================================================
-- 002-legacy-compat-view fixture 1: the "old wide table" (~19 columns) standing in
-- for the real 80-column loan-provisioning table this feature exists to reconstruct
-- the shape of (spec.md's motivating scenario). Still "live" — never written to by
-- this feature; only introspected (legacy_shape_capture) and read (reconciliation).
-- ============================================================================
IF OBJECT_ID('dbo.legacy_loan_application', 'U') IS NOT NULL DROP TABLE dbo.legacy_loan_application;
GO
CREATE TABLE dbo.legacy_loan_application (
    application_id INT PRIMARY KEY,
    applicant_first_name NVARCHAR(100) NOT NULL,
    applicant_last_name NVARCHAR(100) NOT NULL,
    applicant_ssn_last4 NVARCHAR(4) NOT NULL,
    applicant_email NVARCHAR(200) NOT NULL,
    applicant_phone NVARCHAR(20) NOT NULL,
    loan_amount_cents BIGINT NOT NULL,
    loan_purpose NVARCHAR(100) NOT NULL,
    interest_rate_bps INT NOT NULL,
    term_months INT NOT NULL,
    collateral_description NVARCHAR(200) NULL,
    collateral_value_cents BIGINT NULL,
    collateral_type NVARCHAR(50) NULL,
    underwriter_name NVARCHAR(150) NOT NULL,
    underwriting_decision NVARCHAR(50) NOT NULL,
    underwriting_score INT NOT NULL,
    document_ref_number NVARCHAR(100) NOT NULL,
    application_date DATE NOT NULL,
    status NVARCHAR(50) NOT NULL
);
GO

INSERT INTO dbo.legacy_loan_application (
    application_id, applicant_first_name, applicant_last_name, applicant_ssn_last4,
    applicant_email, applicant_phone, loan_amount_cents, loan_purpose, interest_rate_bps,
    term_months, collateral_description, collateral_value_cents, collateral_type,
    underwriter_name, underwriting_decision, underwriting_score, document_ref_number,
    application_date, status
) VALUES
    (1, 'Ada', 'Lovelace', '1234', 'ada.lovelace@example.com', '555-0101', 25000000, 'Home Purchase', 425, 360, '123 Analytical Engine Way', 32000000, 'RealEstate', 'Grace Hopper', 'Approved', 780, 'DOC-0001', '2024-01-10', 'Funded'),
    (2, 'Alan', 'Turing', '2345', 'alan.turing@example.com', '555-0102', 1800000, 'Auto', 599, 60, '2022 Sedan', 2100000, 'Vehicle', 'Grace Hopper', 'Approved', 710, 'DOC-0002', '2024-01-12', 'Funded'),
    (3, 'Katherine', 'Johnson', '3456', 'katherine.johnson@example.com', '555-0103', 45000000, 'Business Expansion', 675, 120, 'Commercial Building', 60000000, 'RealEstate', 'Margaret Hamilton', 'Approved', 745, 'DOC-0003', '2024-01-18', 'Funded'),
    (4, 'Barbara', 'Liskov', '4567', 'barbara.liskov@example.com', '555-0104', 500000, 'Personal', 899, 36, NULL, NULL, NULL, 'Margaret Hamilton', 'Denied', 590, 'DOC-0004', '2024-01-20', 'Closed'),
    (5, 'Radia', 'Perlman', '5678', 'radia.perlman@example.com', '555-0105', 12000000, 'Home Equity', 512, 180, 'Second Lien Residence', 18000000, 'RealEstate', 'Grace Hopper', 'Approved', 760, 'DOC-0005', '2024-02-01', 'Funded'),
    (6, 'Frances', 'Allen', '6789', 'frances.allen@example.com', '555-0106', 2200000, 'Auto', 549, 72, '2023 Truck', 2450000, 'Vehicle', 'Margaret Hamilton', 'Approved', 700, 'DOC-0006', '2024-02-05', 'Funded'),
    (7, 'Shafi', 'Goldwasser', '7890', 'shafi.goldwasser@example.com', '555-0107', 8000000, 'Business Expansion', 610, 84, 'Office Equipment', 9000000, 'Equipment', 'Grace Hopper', 'Approved', 690, 'DOC-0007', '2024-02-14', 'Funded'),
    (8, 'Adele', 'Goldberg', '8901', 'adele.goldberg@example.com', '555-0108', 350000, 'Personal', 950, 24, NULL, NULL, NULL, 'Margaret Hamilton', 'Approved', 650, 'DOC-0008', '2024-02-20', 'Funded'),
    (9, 'Jean', 'Bartik', '9012', 'jean.bartik@example.com', '555-0109', 30000000, 'Home Purchase', 439, 360, '456 Colossus Court', 38000000, 'RealEstate', 'Grace Hopper', 'Approved', 800, 'DOC-0009', '2024-03-01', 'Funded'),
    (10, 'Kathleen', 'Booth', '0123', 'kathleen.booth@example.com', '555-0110', 1500000, 'Auto', 575, 60, '2021 SUV', 1750000, 'Vehicle', 'Margaret Hamilton', 'Approved', 715, 'DOC-0010', '2024-03-05', 'Funded');
GO

-- ============================================================================
-- 002-legacy-compat-view fixture 2: the 5-table normalized replacement schema,
-- joined by a shared application_id (research.md §4 star join), holding the exact
-- same data as dbo.legacy_loan_application above split across tables.
-- ============================================================================
IF OBJECT_ID('dbo.loan_application', 'U') IS NOT NULL DROP TABLE dbo.loan_application;
GO
CREATE TABLE dbo.loan_application (
    application_id INT PRIMARY KEY,
    loan_amount_cents BIGINT NOT NULL,
    loan_purpose NVARCHAR(100) NOT NULL,
    interest_rate_bps INT NOT NULL,
    term_months INT NOT NULL,
    application_date DATE NOT NULL,
    status NVARCHAR(50) NOT NULL
);
GO

IF OBJECT_ID('dbo.loan_applicant', 'U') IS NOT NULL DROP TABLE dbo.loan_applicant;
GO
CREATE TABLE dbo.loan_applicant (
    application_id INT PRIMARY KEY REFERENCES dbo.loan_application(application_id),
    first_name NVARCHAR(100) NOT NULL,
    last_name NVARCHAR(100) NOT NULL,
    ssn_last4 NVARCHAR(4) NOT NULL,
    email NVARCHAR(200) NOT NULL,
    phone NVARCHAR(20) NOT NULL
);
GO

IF OBJECT_ID('dbo.loan_collateral', 'U') IS NOT NULL DROP TABLE dbo.loan_collateral;
GO
CREATE TABLE dbo.loan_collateral (
    application_id INT PRIMARY KEY REFERENCES dbo.loan_application(application_id),
    description NVARCHAR(200) NULL,
    value_cents BIGINT NULL,
    collateral_type NVARCHAR(50) NULL
);
GO

IF OBJECT_ID('dbo.loan_underwriting', 'U') IS NOT NULL DROP TABLE dbo.loan_underwriting;
GO
CREATE TABLE dbo.loan_underwriting (
    application_id INT PRIMARY KEY REFERENCES dbo.loan_application(application_id),
    underwriter_name NVARCHAR(150) NOT NULL,
    decision NVARCHAR(50) NOT NULL,
    score INT NOT NULL
);
GO

IF OBJECT_ID('dbo.loan_document_ref', 'U') IS NOT NULL DROP TABLE dbo.loan_document_ref;
GO
CREATE TABLE dbo.loan_document_ref (
    application_id INT PRIMARY KEY REFERENCES dbo.loan_application(application_id),
    document_ref_number NVARCHAR(100) NOT NULL
);
GO

INSERT INTO dbo.loan_application (application_id, loan_amount_cents, loan_purpose, interest_rate_bps, term_months, application_date, status) VALUES
    (1, 25000000, 'Home Purchase', 425, 360, '2024-01-10', 'Funded'),
    (2, 1800000, 'Auto', 599, 60, '2024-01-12', 'Funded'),
    (3, 45000000, 'Business Expansion', 675, 120, '2024-01-18', 'Funded'),
    (4, 500000, 'Personal', 899, 36, '2024-01-20', 'Closed'),
    (5, 12000000, 'Home Equity', 512, 180, '2024-02-01', 'Funded'),
    (6, 2200000, 'Auto', 549, 72, '2024-02-05', 'Funded'),
    (7, 8000000, 'Business Expansion', 610, 84, '2024-02-14', 'Funded'),
    (8, 350000, 'Personal', 950, 24, '2024-02-20', 'Funded'),
    (9, 30000000, 'Home Purchase', 439, 360, '2024-03-01', 'Funded'),
    (10, 1500000, 'Auto', 575, 60, '2024-03-05', 'Funded');
GO

INSERT INTO dbo.loan_applicant (application_id, first_name, last_name, ssn_last4, email, phone) VALUES
    (1, 'Ada', 'Lovelace', '1234', 'ada.lovelace@example.com', '555-0101'),
    (2, 'Alan', 'Turing', '2345', 'alan.turing@example.com', '555-0102'),
    (3, 'Katherine', 'Johnson', '3456', 'katherine.johnson@example.com', '555-0103'),
    (4, 'Barbara', 'Liskov', '4567', 'barbara.liskov@example.com', '555-0104'),
    (5, 'Radia', 'Perlman', '5678', 'radia.perlman@example.com', '555-0105'),
    (6, 'Frances', 'Allen', '6789', 'frances.allen@example.com', '555-0106'),
    (7, 'Shafi', 'Goldwasser', '7890', 'shafi.goldwasser@example.com', '555-0107'),
    (8, 'Adele', 'Goldberg', '8901', 'adele.goldberg@example.com', '555-0108'),
    (9, 'Jean', 'Bartik', '9012', 'jean.bartik@example.com', '555-0109'),
    (10, 'Kathleen', 'Booth', '0123', 'kathleen.booth@example.com', '555-0110');
GO

INSERT INTO dbo.loan_collateral (application_id, description, value_cents, collateral_type) VALUES
    (1, '123 Analytical Engine Way', 32000000, 'RealEstate'),
    (2, '2022 Sedan', 2100000, 'Vehicle'),
    (3, 'Commercial Building', 60000000, 'RealEstate'),
    (4, NULL, NULL, NULL),
    (5, 'Second Lien Residence', 18000000, 'RealEstate'),
    (6, '2023 Truck', 2450000, 'Vehicle'),
    (7, 'Office Equipment', 9000000, 'Equipment'),
    (8, NULL, NULL, NULL),
    (9, '456 Colossus Court', 38000000, 'RealEstate'),
    (10, '2021 SUV', 1750000, 'Vehicle');
GO

INSERT INTO dbo.loan_underwriting (application_id, underwriter_name, decision, score) VALUES
    (1, 'Grace Hopper', 'Approved', 780),
    (2, 'Grace Hopper', 'Approved', 710),
    (3, 'Margaret Hamilton', 'Approved', 745),
    (4, 'Margaret Hamilton', 'Denied', 590),
    (5, 'Grace Hopper', 'Approved', 760),
    (6, 'Margaret Hamilton', 'Approved', 700),
    (7, 'Grace Hopper', 'Approved', 690),
    (8, 'Margaret Hamilton', 'Approved', 650),
    (9, 'Grace Hopper', 'Approved', 800),
    (10, 'Margaret Hamilton', 'Approved', 715);
GO

INSERT INTO dbo.loan_document_ref (application_id, document_ref_number) VALUES
    (1, 'DOC-0001'), (2, 'DOC-0002'), (3, 'DOC-0003'), (4, 'DOC-0004'), (5, 'DOC-0005'),
    (6, 'DOC-0006'), (7, 'DOC-0007'), (8, 'DOC-0008'), (9, 'DOC-0009'), (10, 'DOC-0010');
GO

-- ============================================================================
-- 002-legacy-compat-view fixture 3: legacy XML document store (US4 fallback
-- lookup). Documents exist for application_id 1-9; application_id 10 has NO
-- document at all (exercises the "document_not_found" outcome). Application 5's
-- document deliberately omits <CollateralValue> — mirroring the same row's NULL
-- collateral value_cents in the normalized schema above — so a field-mapping
-- lookup against it exercises "field_missing" (document exists, field absent)
-- rather than "found", per quickstart.md.
-- ============================================================================
IF OBJECT_ID('dbo.legacy_application_xml', 'U') IS NOT NULL DROP TABLE dbo.legacy_application_xml;
GO
CREATE TABLE dbo.legacy_application_xml (
    application_id INT PRIMARY KEY,
    xml_payload XML NOT NULL
);
GO

INSERT INTO dbo.legacy_application_xml (application_id, xml_payload) VALUES
    (1, '<Application><CollateralValue>32000000</CollateralValue><UnderwritingScore>780</UnderwritingScore></Application>'),
    (2, '<Application><CollateralValue>2100000</CollateralValue><UnderwritingScore>710</UnderwritingScore></Application>'),
    (3, '<Application><CollateralValue>60000000</CollateralValue><UnderwritingScore>745</UnderwritingScore></Application>'),
    (4, '<Application><CollateralValue></CollateralValue><UnderwritingScore>590</UnderwritingScore></Application>'),
    (5, '<Application><UnderwritingScore>760</UnderwritingScore></Application>'),
    (6, '<Application><CollateralValue>2450000</CollateralValue><UnderwritingScore>700</UnderwritingScore></Application>'),
    (7, '<Application><CollateralValue>9000000</CollateralValue><UnderwritingScore>690</UnderwritingScore></Application>'),
    (8, '<Application><CollateralValue></CollateralValue><UnderwritingScore>650</UnderwritingScore></Application>'),
    (9, '<Application><CollateralValue>38000000</CollateralValue><UnderwritingScore>800</UnderwritingScore></Application>');
GO
