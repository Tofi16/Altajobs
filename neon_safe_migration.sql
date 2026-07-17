BEGIN;

-- ------------------------------------------------------------------
-- 1. UPGRADE 'users' TABLE SAFELY (Adds admin & policy features if missing)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS strikes INT DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trust_score INT DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN DEFAULT FALSE;

-- ------------------------------------------------------------------
-- 2. UPGRADE 'wallets' TABLE SAFELY (Adds escrow mechanism if missing)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wallets (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    balance DECIMAL(15, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE wallets ADD COLUMN IF NOT EXISTS escrow_balance DECIMAL(15, 2) DEFAULT 0.00;

-- ------------------------------------------------------------------
-- 3. UPGRADE 'products' TABLE SAFELY (Adds location & approval states if missing)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE products ADD COLUMN IF NOT EXISTS location VARCHAR(100) DEFAULT 'Addis Ababa';
ALTER TABLE products ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';

-- ------------------------------------------------------------------
-- 4. CREATE NEW CORE TABLES IF THEY DO NOT EXIST (No data impact)
-- ------------------------------------------------------------------

-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    wallet_id INT NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Offers (Negotiation System) Table
CREATE TABLE IF NOT EXISTS offers (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    buyer_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seller_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    offered_price DECIMAL(15, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Announcements Table
CREATE TABLE IF NOT EXISTS announcements (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    image_url VARCHAR(255) DEFAULT NULL,
    is_pinned BOOLEAN DEFAULT FALSE,
    view_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Restricted Words Table
CREATE TABLE IF NOT EXISTS restricted_words (
    id SERIAL PRIMARY KEY,
    word VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------
-- 5. SEED OR UPDATE ADMIN 'Tofik' SAFELY
-- ------------------------------------------------------------------
-- Upsert Admin 'Tofik'. If Tofik already exists, simply ensure they are set to 'admin' role.
INSERT INTO users (username, password_hash, role)
VALUES ('Tofik', '$2b$10$PlaceholderHashForTofikSecuredPassword123', 'admin')
ON CONFLICT (username) 
DO UPDATE SET role = 'admin';

-- Safely initialize a wallet for Admin 'Tofik' only if they do not have one.
INSERT INTO wallets (user_id, balance)
SELECT id, 0.00 FROM users WHERE username = 'Tofik'
ON CONFLICT (user_id) 
DO NOTHING;

COMMIT;
