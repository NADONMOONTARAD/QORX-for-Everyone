-- =============================================================
-- setup_schema.sql  –  สร้างตารางทั้งหมดตาม models.py (Source of Truth)
-- ไฟล์นี้ถูก generate ให้ตรงกับ Supabase schema ล่าสุด
-- รันได้ทั้ง DBeaver (localhost) และ Supabase
-- =============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. stocks ─ ข้อมูลพื้นฐานของหุ้น
CREATE TABLE IF NOT EXISTS stocks (
    ticker                  TEXT PRIMARY KEY,
    company_name            TEXT NOT NULL,
    sector                  TEXT,
    industry                TEXT,
    market_cap              BIGINT,
    logo_url                TEXT,
    last_updated            TIMESTAMPTZ DEFAULT NOW(),
    is_active               BOOLEAN DEFAULT TRUE
);

-- Migration: add logo_url if it doesn't exist yet (for existing databases)
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS logo_url TEXT;

-- 2. sec_filings_metadata ─ Metadata เอกสาร SEC
CREATE TABLE IF NOT EXISTS sec_filings_metadata (
    filing_id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker                  TEXT NOT NULL,
    form_type               TEXT NOT NULL,
    filing_date             DATE NOT NULL,
    report_date             DATE,
    sec_url                 TEXT NOT NULL UNIQUE
);

-- 3. financial_data ─ งบการเงิน (Annual + Quarterly)
CREATE TABLE IF NOT EXISTS financial_data (
    financial_data_id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker                              TEXT NOT NULL,
    report_date                         DATE NOT NULL,
    period_type                         TEXT NOT NULL,

    -- Raw Data Fields
    total_revenue                       BIGINT,
    net_income                          BIGINT,
    total_assets                        BIGINT,
    total_liabilities                   BIGINT,
    share_outstanding_diluted           BIGINT,
    shares_repurchased                  NUMERIC(20, 4),
    total_cost_of_buybacks              NUMERIC(20, 2),
    avg_buyback_price                   NUMERIC(15, 4),
    interest_bearing_debt               BIGINT,
    cash_and_equivalents                BIGINT,
    goodwill_and_intangibles            BIGINT,
    selling_general_and_admin_expense   BIGINT,
    depreciation_and_amortization       BIGINT,
    property_plant_and_equipment_net    BIGINT,
    accounts_receivable                 BIGINT,
    inventory                           BIGINT,
    accounts_payable                    BIGINT,
    current_assets                      BIGINT,
    current_liabilities                 BIGINT,
    stock_based_compensation            BIGINT,
    deferred_income_tax                 BIGINT,
    other_non_cash_items                BIGINT,
    operating_income                    BIGINT,
    income_tax_expense                  BIGINT,
    cash_flow_from_operations           BIGINT,
    capital_expenditures                BIGINT,
    gross_profit                        BIGINT,
    interest_expense                    BIGINT,
    premiums_earned                     BIGINT,
    losses_incurred                     BIGINT,
    dividends_paid                      BIGINT,

    -- Calculated Metrics
    roe                                 NUMERIC(10, 4),
    roic                                NUMERIC(10, 4),
    debt_to_equity                      NUMERIC(10, 4),
    free_cash_flow                      BIGINT,
    eps_diluted                         NUMERIC(10, 4),
    revenue_growth                      NUMERIC(10, 4),
    eps_growth_diluted                  NUMERIC(10, 4),
    fcf_growth                          NUMERIC(10, 4),
    gross_margin                        NUMERIC(10, 4),
    net_profit_margin                   NUMERIC(10, 4),
    fcf_margin                          NUMERIC(10, 4),
    interest_coverage                   NUMERIC(10, 4),
    combined_ratio                      NUMERIC(10, 4),
    payout_ratio                        NUMERIC(10, 4),
    expense_ratio                       NUMERIC(10, 4),
    nav_price                           NUMERIC(15, 4),
    dividend_yield                      NUMERIC(10, 4),
    ytd_return                          NUMERIC(10, 4),
    three_year_return                   NUMERIC(10, 4),
    five_year_return                    NUMERIC(10, 4),
    intrinsic_value_estimate            NUMERIC(15, 2),

    data_source                         TEXT NOT NULL,
    last_updated                        TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT financial_data_unique_key
        UNIQUE (ticker, report_date, period_type)
);

-- Migration: add fund columns if they do not exist
ALTER TABLE financial_data ADD COLUMN IF NOT EXISTS expense_ratio NUMERIC(10, 4);
ALTER TABLE financial_data ADD COLUMN IF NOT EXISTS nav_price NUMERIC(15, 4);
ALTER TABLE financial_data ADD COLUMN IF NOT EXISTS dividend_yield NUMERIC(10, 4);
ALTER TABLE financial_data ADD COLUMN IF NOT EXISTS ytd_return NUMERIC(10, 4);
ALTER TABLE financial_data ADD COLUMN IF NOT EXISTS three_year_return NUMERIC(10, 4);
ALTER TABLE financial_data ADD COLUMN IF NOT EXISTS five_year_return NUMERIC(10, 4);

-- 4. stock_analysis_results ─ ผลการวิเคราะห์หุ้น
CREATE TABLE IF NOT EXISTS stock_analysis_results (
    analysis_id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker                      TEXT NOT NULL UNIQUE,
    analysis_date               TIMESTAMPTZ DEFAULT NOW(),
    moat_rating                 TEXT,
    conviction_score            NUMERIC(5, 2),
    key_risks                   TEXT,
    intrinsic_value_estimate    NUMERIC(15, 2),
    intrinsic_value_reason      TEXT,
    ai_recommendation_summary   TEXT,
    ai_reasoning                JSONB,
    portfolio_directive         JSONB,
    margin_of_safety            NUMERIC(7, 4),
    current_price               NUMERIC(15, 4),
    checklist_details           JSONB,
    model_used                  TEXT
);

-- Migration: add model_used if it does not exist yet
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS model_used TEXT;

-- 5. document_summaries ─ สรุปเอกสารจาก AI
CREATE TABLE IF NOT EXISTS document_summaries (
    filing_id               UUID PRIMARY KEY REFERENCES sec_filings_metadata(filing_id),
    gemini_summary_json     JSONB,
    ai_model                TEXT,
    last_updated            TIMESTAMPTZ DEFAULT NOW()
);

-- 6. product_segment_revenues ─ รายได้แยกตามกลุ่มผลิตภัณฑ์
CREATE TABLE IF NOT EXISTS product_segment_revenues (
    segment_revenue_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker                  TEXT NOT NULL,
    report_date             DATE NOT NULL,
    period_type             TEXT NOT NULL,
    segment_original_name   TEXT NOT NULL,
    segment_group           TEXT NOT NULL,
    revenue_amount          BIGINT,
    revenue_amount_raw      NUMERIC(20, 6),
    revenue_unit            TEXT,
    ai_confidence           NUMERIC(5, 4),
    revenue_growth_pct      NUMERIC(10, 4),
    data_source             TEXT,
    last_updated            TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT product_segment_revenues_unique_key
        UNIQUE (ticker, report_date, period_type, segment_group)
);

-- 7. geo_segment_revenues ─ รายได้แยกตามภูมิศาสตร์
CREATE TABLE IF NOT EXISTS geo_segment_revenues (
    segment_revenue_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker                  TEXT NOT NULL,
    report_date             DATE NOT NULL,
    period_type             TEXT NOT NULL,
    segment_original_name   TEXT NOT NULL,
    segment_group           TEXT NOT NULL,
    revenue_amount          BIGINT,
    revenue_amount_raw      NUMERIC(20, 6),
    revenue_unit            TEXT,
    ai_confidence           NUMERIC(5, 4),
    revenue_growth_pct      NUMERIC(10, 4),
    data_source             TEXT,
    last_updated            TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT geo_segment_revenues_unique_key
        UNIQUE (ticker, report_date, period_type, segment_group)
);

-- 8. system_status ─ Key-value สถานะ pipeline
CREATE TABLE IF NOT EXISTS system_status (
    key                     TEXT PRIMARY KEY,
    value                   JSONB,
    last_updated            TIMESTAMPTZ DEFAULT NOW()
);

-- 10. portfolio_state ─ สถานะพอร์ตรวม
CREATE TABLE IF NOT EXISTS portfolio_state (
    state_id                INT PRIMARY KEY,
    portfolio_value         NUMERIC(18, 4),
    portfolio_peak          NUMERIC(18, 4),
    start_value             NUMERIC(18, 4),
    start_date              DATE,
    total_days              INT,
    sum_return              NUMERIC(18, 6),
    sum_squared_diff        NUMERIC(18, 6),
    risk_free_rate          NUMERIC(10, 4),
    sharpe_ratio            NUMERIC(10, 4),
    cagr                    NUMERIC(10, 4),
    max_drawdown            NUMERIC(10, 4),
    total_return            NUMERIC(10, 4),
    last_update             DATE,
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- 11. portfolio_checkpoints ─ Snapshot พอร์ตรายเดือน
CREATE TABLE IF NOT EXISTS portfolio_checkpoints (
    id                      SERIAL PRIMARY KEY,
    year                    INT NOT NULL,
    month                   INT NOT NULL,
    portfolio_value         NUMERIC(18, 4),
    cagr                    NUMERIC(10, 4),
    sharpe                  NUMERIC(10, 4),
    drawdown                NUMERIC(10, 4),
    total_return            NUMERIC(10, 4),
    created_at              TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT portfolio_checkpoints_year_month_key
        UNIQUE (year, month)
);

-- 12. transactions ─ ประวัติธุรกรรม
CREATE TABLE IF NOT EXISTS transactions (
    id                      SERIAL PRIMARY KEY,
    date                    DATE NOT NULL,
    ticker                  TEXT,
    type                    TEXT NOT NULL,
    amount                  NUMERIC(18, 4),
    price                   NUMERIC(15, 4),
    quantity                NUMERIC(18, 6),
    cash_after              NUMERIC(18, 4),
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- 13. portfolio_positions ─ ตำแหน่งถือครองในพอร์ต
CREATE TABLE IF NOT EXISTS portfolio_positions (
    ticker                      TEXT PRIMARY KEY,
    analysis_date               TIMESTAMPTZ,
    conviction_score            NUMERIC(5, 2),
    conviction_baseline_score   NUMERIC(5, 2),
    conviction_baseline_date    DATE,
    conviction_change_pct       NUMERIC(7, 3),
    margin_of_safety            NUMERIC(7, 4),
    mos_baseline_value          NUMERIC(7, 4),
    mos_baseline_date           DATE,
    mos_change_pct              NUMERIC(7, 3),
    current_price               NUMERIC(15, 4),
    quantity                    NUMERIC(18, 6),
    cost_basis                  NUMERIC(18, 4),
    current_value               NUMERIC(18, 4),
    current_pct                 NUMERIC(7, 3),
    target_pct                  NUMERIC(7, 3),
    delta_pct                   NUMERIC(7, 3),
    total_return                NUMERIC(10, 4),
    action_label                TEXT,
    action                      TEXT,
    reallocation_flag           BOOLEAN DEFAULT FALSE,
    details                     JSONB,
    last_updated                TIMESTAMPTZ DEFAULT NOW()
);

-- INDEXES FOR PERFORMANCE
CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker ON sec_filings_metadata(ticker);
CREATE INDEX IF NOT EXISTS idx_financial_data_ticker ON financial_data(ticker);
CREATE INDEX IF NOT EXISTS idx_analysis_results_ticker ON stock_analysis_results(ticker);

-- =============================================================
-- USER PROFILES  ─  เก็บข้อมูลผู้ใช้ (เชื่อมกับ Supabase Auth)
-- ข้อมูล full_name / avatar_url ดึงมาจาก Google OAuth อัตโนมัติ
-- =============================================================

CREATE TABLE IF NOT EXISTS public.profiles (
    id          UUID REFERENCES auth.users ON DELETE CASCADE NOT NULL PRIMARY KEY,
    full_name   TEXT,
    avatar_url  TEXT,
    plan        TEXT NOT NULL DEFAULT 'free',   -- 'free' | 'pro'
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security: ผู้ใช้แก้ไขได้เฉพาะโปรไฟล์ตัวเอง
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Select
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
CREATE POLICY "profiles_select_own"
    ON public.profiles FOR SELECT USING (auth.uid() = id);

-- Insert (จำเป็นสำหรับการ upsert ครั้งแรกของบัญชีเก่า)
DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;
CREATE POLICY "profiles_insert_own"
    ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);

-- Update
DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
CREATE POLICY "profiles_update_own"
    ON public.profiles FOR UPDATE USING (auth.uid() = id);

-- Delete (กู้คืนพื้นที่ หรือลบข้อมูลส่วนตัว)
DROP POLICY IF EXISTS "profiles_delete_own" ON public.profiles;
CREATE POLICY "profiles_delete_own"
    ON public.profiles FOR DELETE USING (auth.uid() = id);

-- Trigger: สร้าง profile อัตโนมัติทุกครั้งที่มีผู้ใช้ใหม่สมัครบัญชี (รองรับ Google OAuth ด้วย)
-- ข้อมูล full_name และ avatar_url จะถูกดึงจาก Google โดยอัตโนมัติ
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.raw_user_meta_data->>'full_name',
        NEW.raw_user_meta_data->>'avatar_url'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Drop and recreate trigger to avoid duplicates on re-run
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
