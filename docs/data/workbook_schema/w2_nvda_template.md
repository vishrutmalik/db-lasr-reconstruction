# W2 catalog — ASQ Comprehensive Financial Data NVDA (v3)

Goal G012. Source: `inputs/data_templates/ASQ_Comprehensive_Financial_Data_NVDA_v3.xlsx`
SHA-256: `40973092c8a3f598336fc28a168c664cfeee387d584ef14da5ad7e7c7bf83b22`
A filled example of the AlphaSense company template for ticker NVDA. Extraction: openpyxl 3.1.5, values + formula passes. Sheets: `Front Page` (B1:N44), `Financial Statements` (B1:M337), `Ratios` (B1:M150), `Trading Multiples` (B1:BB1678), `Data` (A1:T23).

openpyxl reports an unsupported *Data Validation extension* on load — the template's dropdowns (ticker/currency/period selectors) exist but are not machine-readable here; they are documented below from their cell labels and the `Data` sheet lookup lists.

## Template controls (UI, not data fields)

| Location | Control | Observed value | Notes |
|----------|---------|----------------|-------|
| Front Page C3/D3 | `Enter Ticker >>` | `NVDA` | free/dropdown entry; Trading Multiples C3 mirrors it via `='Front Page'!$D$3` |
| Front Page C4/D4 | `Select Currency >>` | `Reporting Currency` | options per `Data!A2:B4`: `Reporting Currency`, `US Dollar (USD)` |
| Front Page C5/D5 | `Select Period >>` | `Fiscal Year` | options per `Data!D2:E5`: `Fiscal Year`→`FY`, `Fiscal Quarter`→`FQ`, `Fiscal Semi-Annual`→`FH` |
| Trading Multiples B4/C4 | `Start Date >>` | 2025-01-01 | user-set window start |
| Trading Multiples B5/C5 | `End Date >>` | 2026-06-21 | user-set window end |
| Data N2:O3 | `Version Type` | `Latest restatement` → `latest_filing` | the only version type present — see PIT assessment |

Support contact shown on Front Page J3:J4: template queries to AlphaSense Support (support@alpha-sense.com).

## Sheet `Front Page` (34 coded fields)

Layout: col B = `excel_code`, col C = label, col D = value. Groups: company reference (rows 7-15), market data (17-27), ratings (29-37), price targets (39-44).

| Row | excel_code | Label | Observed value (NVDA) |
|-----|------------|-------|------------------------|
| 7 | `NAME` | Company Name | NVIDIA Corp |
| 8 | `COUNTRY_HQ` | Country of Headquaters | United States |
| 9 | `TRADING_CURR` | Trading Currency | USD |
| 10 | `SECTOR_GICS` | Sector (GICS L1) | Information Technology |
| 11 | `SUB_INDUSTRY_GICS` | Sub-Sector (GICS L4) | Semiconductors |
| 12 | `REPORTING_CURR` | Reporting Currency | USD |
| 13 | `COUNTRY_EXCH` | Country of Stock Exchange | US |
| 14 | `EXCH` | Stock Exchange | Nasdaq - All Markets |
| 15 | `FINANCIAL_PERIOD_END_DATE` | Financial Period End Date | 2026-04-26 |
| 17 | `CLOSE` | Share Price | (empty) |
| 18 | `CLOSE_LAST` | Last Close Price | (empty) |
| 19 | `VOLUME` | Daily Volume | (empty) |
| 20 | `SHARES_OUTSTANDING` | Shares Outstanding (in mm) | (empty) |
| 22 | `52WK_HIGH` | 52 Week High | (empty) |
| 23 | `52WK_HIGH_PCT_CHG` | 52 Week High Change, % | (empty) |
| 24 | `52WK_HIGH_DATE` | 52 Week High Date | (empty) |
| 25 | `52WK_LOW` | 52 Week Low | (empty) |
| 26 | `52WK_LOW_PCT_CHG` | 52 Week Low Change, % | (empty) |
| 27 | `52WK_LOW_DATE` | 52 Week Low Date | (empty) |
| 29 | `RATING_LABEL` | Rating - Label | (empty) |
| 30 | `RATING_NUM_STRONG_BUYS` | Rating - Number of Strong Buys | (empty) |
| 31 | `RATING_NUM_BUYS` | Rating - Number of Buys | (empty) |
| 32 | `RATING_NUM_HOLDS` | Rating - Number of Holds | (empty) |
| 33 | `RATING_NUM_SELLS` | Rating - Number of Sells | (empty) |
| 34 | `RATING_NUM_STRONG_SELLS` | Rating - Number of Strong Sells | (empty) |
| 35 | `RATING_MEAN` | Rating - Mean Recommendation | (empty) |
| 36 | `RATING_NO_OPINION` | Rating - No Opinion | (empty) |
| 37 | `RATING_NUM_RECOMMENDATIONS` | Rating - Number of Recommendations | VL40: Unknown metric "RATING_NUM_RECOMMENDATIONS" |
| 39 | `PRICE_TARGET` | Price Target - Mean | (empty) |
| 40 | `PRICE_TARGET_MEDIAN` | Price Target - Median | (empty) |
| 41 | `PRICE_TARGET_LOW` | Price Target - Low | (empty) |
| 42 | `PRICE_TARGET_HIGH` | Price Target - High | (empty) |
| 43 | `PRICE_TARGET_CONTRIBUTORS` | Price Target - Number of Contributors | (empty) |
| 44 | `PRICE_TARGET_SD` | Price Target - Standard Deviation | (empty) |

Notes: 24 of 34 fields are empty in this saved copy (market data, ratings, price targets) — the template populates them live via an add-in; cached values were not saved. Row 37 D37 contains the literal error string `VL40: Unknown metric "RATING_NUM_RECOMMENDATIONS"`, i.e. the add-in rejected that code — evidence the codes are resolved server-side and this one is invalid/renamed.

## Sheets `Financial Statements` and `Ratios` — layout

- Col B = `excel_code`, col C = label; cols D-K = **relative periods FY-5..FY+2** (8 columns).
- Row 4 builds the labels via formula `=Data!E1&{-5..2}` (`Data!E1` = selected period code `FY`); with `Select Period` set to FQ/FH the same 8 columns would be FQ-5..FQ+2 / FH-5..FH+2 — the window is always 6 back + 2 forward relative periods.
- Row 5 `FINANCIAL_PERIOD_END_DATE`: FY-5=2021-01-31, FY-4=2022-01-30, FY-3=2023-01-29, FY-2=2024-01-28, FY-1=2025-01-26, FY0=2026-01-25, FY1=2027-01-31, FY2=2028-01-31 (NVDA fiscal years ending late Jan).
- FY1/FY2 columns hold **forward estimates** (non-integer consensus-style values, e.g. `REV` FY1 = 393594.53), so the grid mixes actuals (FY-5..FY0) and consensus (FY+1..FY+2) in one layout.
- Money values are in **millions of the selected currency** (NVDA `REV` FY-5 = 16675 ~ USD 16.675bn FY2021); percent metrics labeled `, %`; multiples dimensionless.
- Cols L/M are empty on both sheets (extent padding).

Non-null NVDA values per period column - Financial Statements: FY-5:92, FY-4:102, FY-3:103, FY-2:102, FY-1:102, FY0:100, FY1:63, FY2:63

Non-null per period - Ratios: FY-5:21, FY-4:21, FY-3:21, FY-2:21, FY-1:21, FY0:21, FY1:15, FY2:15

### `Financial Statements` metric inventory (rows 8-337: 306 coded metric rows + 14 section headers + 10 blank rows = 330)

| Row | excel_code | Label | Statement grouping | NVDA non-null periods (of 8) |
|-----|------------|-------|--------------------|------------------------------|
| 8 | `REV` | Revenue | INCOME STATEMENT | 8 |
| 9 | `REV_ADJMT` | Revenue Adjustments | INCOME STATEMENT | 0 |
| 10 | `REV_ADJ` | Adj. Revenue | INCOME STATEMENT | 0 |
| 11 | `OTHER_REVENUE` | Other Revenue | INCOME STATEMENT | 0 |
| 12 | `INC_DIV` | Dividend Income | INCOME STATEMENT | 0 |
| 13 | `NON_INT_REV` | Non-Interest Revenue | INCOME STATEMENT | 0 |
| 14 | `OTHER_NON_INT_REV` | Other Non-Interest Revenue | INCOME STATEMENT | 0 |
| 15 | `COGS` | Cost of Goods Sold | INCOME STATEMENT | 6 |
| 16 | `COGS_ADJMT` | Cost of Goods Sold Adjustments | INCOME STATEMENT | 0 |
| 17 | `COGS_ADJ` | Adj. Cost of Goods Sold | INCOME STATEMENT | 0 |
| 18 | `GP` | Gross Profit | INCOME STATEMENT | 6 |
| 19 | `GP_ADJMT` | Gross Profit Adjustments | INCOME STATEMENT | 0 |
| 20 | `GP_ADJ` | Adj. Gross Profit | INCOME STATEMENT | 8 |
| 21 | `SGA_EXP` | Selling, General and Administrative Expense | INCOME STATEMENT | 8 |
| 22 | `SM_EXP` | Selling and Marketing Expense | INCOME STATEMENT | 0 |
| 23 | `GA_EXP` | General and Administrative Expense | INCOME STATEMENT | 0 |
| 24 | `STAFF_COSTS` | Staff Costs | INCOME STATEMENT | 0 |
| 25 | `COMPENSATION_EXP` | Compensation Expense | INCOME STATEMENT | 0 |
| 26 | `OCCUPANCY_EQUIPMENT_EXP` | Occupancy and Equipment Expense | INCOME STATEMENT | 0 |
| 27 | `PROFESSIONAL_EXP` | Professional Expenses | INCOME STATEMENT | 0 |
| 28 | `OTHER_SG&A_EXP` | Other SG&A Expenses | INCOME STATEMENT | 0 |
| 29 | `SGA_EXP_ADJMT` | Selling, General and Administrative Expense Adjustments | INCOME STATEMENT | 0 |
| 30 | `SGA_EXP_ADJ` | Adj. Selling, General and Administrative Expense | INCOME STATEMENT | 0 |
| 31 | `RD_EXP` | Research and Development Expense | INCOME STATEMENT | 8 |
| 32 | `RD_EXP_ADJMT` | Research and Development Expense Adjustments | INCOME STATEMENT | 0 |
| 33 | `RD_EXP_ADJ` | Adj. Research and Development Expense | INCOME STATEMENT | 0 |
| 34 | `OP_EXP_OTH` | Other Operating Expenses | INCOME STATEMENT | 5 |
| 35 | `OP_EXP_OTH_ADJMT` | Other Operating Adjustments | INCOME STATEMENT | 0 |
| 36 | `OTHER_NONINT_EXP` | Other Non-Interest Expense | INCOME STATEMENT | 0 |
| 37 | `TOTAL_NON_INT_EXP` | Total Non-Interest Expense | INCOME STATEMENT | 0 |
| 38 | `EBITDA` | EBITDA | INCOME STATEMENT | 8 |
| 39 | `EBITDA_ADJMT` | EBITDA Adjustments | INCOME STATEMENT | 0 |
| 40 | `OTH_EBITDA_ADJMT` | Other Adjustments to EBITDA | INCOME STATEMENT | 0 |
| 41 | `EBITDA_ADJ` | Adj. EBITDA | INCOME STATEMENT | 8 |
| 42 | `DA_EXP_OP` | Depreciation and Amortization Expense | INCOME STATEMENT | 0 |
| 43 | `DEP` | Depreciation | INCOME STATEMENT | 0 |
| 44 | `AMORT` | Amortization | INCOME STATEMENT | 0 |
| 45 | `DA_EXP_OP_ADJMT` | Depreciation and Amortization Expense Adjustments | INCOME STATEMENT | 0 |
| 46 | `DA_EXP_OP_ADJ` | Adj. Depreciation and Amortization Expense | INCOME STATEMENT | 0 |
| 47 | `EBIT` | EBIT | INCOME STATEMENT | 8 |
| 48 | `EBIT_ADJMT` | EBIT Adjustments | INCOME STATEMENT | 0 |
| 49 | `EBIT_ADJ` | Adj. EBIT | INCOME STATEMENT | 8 |
| 50 | `OTHER_INCOME_EXP` | Other Income Expense | INCOME STATEMENT | 0 |
| 51 | `NON_OP_INC_OTH` | Other Non-Operating Income (Expense), Net | INCOME STATEMENT | 6 |
| 52 | `OTHER_NON_OP_ADJMT` | Other Non-Operating Adjustments | INCOME STATEMENT | 0 |
| 53 | `SPECIAL_INCOME_CHARGES` | Special Income Charges | INCOME STATEMENT | 0 |
| 54 | `NET_FOREIGN_EXCHANGE_G&L` | Net Foreign Exchange Gain/Loss | INCOME STATEMENT | 0 |
| 55 | `EBT` | EBT | INCOME STATEMENT | 8 |
| 56 | `EBT_ADJMT` | EBT Adjustments | INCOME STATEMENT | 0 |
| 57 | `EBT_ADJ` | Adj. EBT | INCOME STATEMENT | 0 |
| 58 | `TAX_EXP` | Tax Expense | INCOME STATEMENT | 8 |
| 59 | `TAX_EXP_ADJMT` | Tax Expense Adjustments | INCOME STATEMENT | 0 |
| 60 | `TAX_EXP_ADJ` | Adj. Tax Expense | INCOME STATEMENT | 0 |
| 61 | `TAX_RATE` | Effective Tax Rate | INCOME STATEMENT | 0 |
| 62 | `NI_CONTINOP` | Net Income from Continuous Operations | INCOME STATEMENT | 6 |
| 63 | `NI_DISCONT` | Net Income Discontinuous Operations | INCOME STATEMENT | 0 |
| 64 | `NI_EXTRAORDINARY` | Net Income Extraordinary | INCOME STATEMENT | 0 |
| 65 | `NI_TAX_LOSS` | Net Income from Tax Loss Carry Forward | INCOME STATEMENT | 0 |
| 66 | `EQUITY_INCOME_POST_TAX` | Earnings from Equity Interest Net of Tax | INCOME STATEMENT | 0 |
| 67 | `NI_NCI` | Net Income to NCI | INCOME STATEMENT | 0 |
| 68 | `PREF_STOCK_DIV_AND_OTH` | Preferred Stock Dividends and Other | INCOME STATEMENT | 0 |
| 69 | `NI_BASIC` | Net Income to Common Shareholders | INCOME STATEMENT | 8 |
| 70 | `NI_BASIC_ADJMT` | Net Income to Common Shareholder Adjustments | INCOME STATEMENT | 0 |
| 71 | `NI_BASIC_ADJ` | Adj. Net Income to Common Shareholders | INCOME STATEMENT | 8 |
| 72 | `NI_DILUTION` | Adjustments for Convertible Securities | INCOME STATEMENT | 0 |
| 73 | `NI_DILUTED` | Diluted Net Income to Common Shareholders | INCOME STATEMENT | 8 |
| 74 | `EPS_WAB` | Earnings Per Share - WAB | INCOME STATEMENT | 6 |
| 75 | `EPS_WAD` | Earnings Per Share - WAD | INCOME STATEMENT | 8 |
| 76 | `EPS_WAD_ADJ` | Adj. Earnings Per Share - WAD | INCOME STATEMENT | 8 |
| 77 | `DPS` | Dividends Per Share | INCOME STATEMENT | 7 |
| 80 | `INT_REVENUE` | Interest Revenue | INCOME STATEMENT / Banking & Financial Services | 0 |
| 81 | `INT_INC` | Interest Income | INCOME STATEMENT / Banking & Financial Services | 6 |
| 82 | `INT_INC_LOANS_LEASE` | Interest Income from Loans and Leases | INCOME STATEMENT / Banking & Financial Services | 0 |
| 83 | `INT_INC_SECURITIES` | Interest Income from Securities | INCOME STATEMENT / Banking & Financial Services | 0 |
| 84 | `INT_INC_DEPOSITS` | Interest Income from Deposits | INCOME STATEMENT / Banking & Financial Services | 0 |
| 85 | `OTHER_INT_INC` | Other Interest Income | INCOME STATEMENT / Banking & Financial Services | 0 |
| 86 | `FEES_AND_COMMISSIONS` | Fees and Commissions | INCOME STATEMENT / Banking & Financial Services | 0 |
| 87 | `NET_TRADING_INCOME` | Net Trading Income | INCOME STATEMENT / Banking & Financial Services | 0 |
| 88 | `TRADING_G&L` | Trading Gain/Loss | INCOME STATEMENT / Banking & Financial Services | 0 |
| 89 | `G&L_ON_INVESTMENTS` | Gain/Loss on Investments | INCOME STATEMENT / Banking & Financial Services | 0 |
| 90 | `G&L_ON_DERIVATIVES` | Gain/Loss on Derivatives | INCOME STATEMENT / Banking & Financial Services | 0 |
| 91 | `IB_PROFIT` | Investment Banking Profit | INCOME STATEMENT / Banking & Financial Services | 0 |
| 92 | `NET_INVESTMENT_INCOME` | Net Investment Income | INCOME STATEMENT / Banking & Financial Services | 0 |
| 93 | `NET_INVESTMENT_GAINS` | Net Investment Gains | INCOME STATEMENT / Banking & Financial Services | 0 |
| 94 | `INCOME_FROM_ASSOCIATES` | Income from Associates and Other Participating Interests | INCOME STATEMENT / Banking & Financial Services | 0 |
| 95 | `INT_EXP` | Interest Expense | INCOME STATEMENT / Banking & Financial Services | 6 |
| 96 | `INT_EXP_FOR_DEPOSIT` | Interest Expense for Deposit | INCOME STATEMENT / Banking & Financial Services | 0 |
| 97 | `INT_EXP_LT_DEBT` | Interest Expense for LTD and Capital Securities | INCOME STATEMENT / Banking & Financial Services | 0 |
| 98 | `OTHER_INT_EXP` | Other Interest Expense | INCOME STATEMENT / Banking & Financial Services | 0 |
| 99 | `CREDIT_LOSSES_PROV` | Provision for Credit Losses | INCOME STATEMENT / Banking & Financial Services | 0 |
| 100 | `FEES_AND_COMMISSION_EXP` | Fees and Commission Expense | INCOME STATEMENT / Banking & Financial Services | 0 |
| 101 | `NET_INT_INC` | Net Interest Income | INCOME STATEMENT / Banking & Financial Services | 0 |
| 102 | `INT_INC_NET` | Interest Income (Expense), Net | INCOME STATEMENT / Banking & Financial Services | 8 |
| 103 | `INT_INC_NET_ADJMT` | Interest Income (Expense), Net Adjustments | INCOME STATEMENT / Banking & Financial Services | 0 |
| 104 | `INT_INC_NET_ADJ` | Adj. Interest Income (Expense), Net | INCOME STATEMENT / Banking & Financial Services | 0 |
| 105 | `AMORTIZATION_SECURITIES` | Amortization of Securities | INCOME STATEMENT / Banking & Financial Services | 0 |
| 108 | `GROSS_WRITTEN_PREMIUM` | Gross Premiums Written | INCOME STATEMENT / Insurance | 0 |
| 109 | `CEDED_PREMIUM` | Ceded Premiums | INCOME STATEMENT / Insurance | 0 |
| 110 | `NET_PREMIUMS_WRITTEN` | Net Premiums Written | INCOME STATEMENT / Insurance | 0 |
| 111 | `NET_UNEARNED_PREMIUM` | Change in Net Unearned Premium Reserves | INCOME STATEMENT / Insurance | 0 |
| 112 | `NET_EARNED_PREMIUMS` | Net Earned Premiums | INCOME STATEMENT / Insurance | 0 |
| 113 | `LOSS_AND_LOSS_ADJUSTMENT_EXPENSES` | Loss & Loss Adjustment Expenses | INCOME STATEMENT / Insurance | 0 |
| 114 | `POLICYHOLDER_INT` | Policyholder Interest | INCOME STATEMENT / Insurance | 0 |
| 115 | `UNDERWRITING_EXP` | Underwriting Expenses | INCOME STATEMENT / Insurance | 0 |
| 116 | `POLICYHOLDER_DIVIDENDS` | Policyholder Dividends | INCOME STATEMENT / Insurance | 0 |
| 121 | `CASH_AND_EQUIV` | Cash and Cash Equivalents | Balance Sheet / Assets | 8 |
| 122 | `ST_INVT` | Short Term Investments | Balance Sheet / Assets | 8 |
| 123 | `CASH_AND_ST_INVT` | Cash and Cash Equivalents and Short Term Investments | Balance Sheet / Assets | 8 |
| 124 | `RESTRICTED_CASH_INVESTMENTS` | Restricted Cash and Investments | Balance Sheet / Assets | 0 |
| 125 | `REC_NET` | Receivables, Net | Balance Sheet / Assets | 8 |
| 126 | `ACCT_REC` | Accounts Receivable | Balance Sheet / Assets | 8 |
| 127 | `OTH_REC` | Other Receivables | Balance Sheet / Assets | 5 |
| 128 | `INV_NET` | Total Inventory, Net | Balance Sheet / Assets | 8 |
| 129 | `TAXES_ASSETS_CURRENT` | Current Tax Assets | Balance Sheet / Assets | 0 |
| 130 | `CURR_OTH_ASSET` | Other Current Assets | Balance Sheet / Assets | 6 |
| 131 | `CURR_ASSET` | Total Current Assets | Balance Sheet / Assets | 8 |
| 132 | `PPE_NET` | PP&E, Net | Balance Sheet / Assets | 8 |
| 133 | `GW` | Goodwill | Balance Sheet / Assets | 8 |
| 134 | `INTANGIBLE_EXCL_GW` | Intangible Assets (Excl. Goodwill) | Balance Sheet / Assets | 8 |
| 135 | `INTANGIBLE_INCL_GW` | Intangible Assets (Incl. Goodwill) | Balance Sheet / Assets | 8 |
| 136 | `TOTAL_INVESTMENTS` | Total Investments | Balance Sheet / Assets | 8 |
| 137 | `LT_EQUITY_INVESTMENTS` | Long Term Equity Investment | Balance Sheet / Assets | 0 |
| 138 | `OTHER_INVESTED_ASSETS` | Other Invested Assets | Balance Sheet / Assets | 0 |
| 139 | `DEFERRED_TAX_ASSETS` | Deferred Tax Assets | Balance Sheet / Assets | 0 |
| 140 | `NON_CURR_OTH_ASSET` | Other Non-Current Assets | Balance Sheet / Assets | 6 |
| 141 | `OTHER_ASSETS` | Other Assets | Balance Sheet / Assets | 0 |
| 142 | `NON_CURR_ASSET` | Total Non-Current Assets | Balance Sheet / Assets | 8 |
| 143 | `TOT_ASSET` | Total Assets | Balance Sheet / Assets | 8 |
| 146 | `PAYABLE_AND_CURR_AE` | Accounts Payable and Current Accrued Expenses | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 147 | `ACCT_PAYABLE` | Accounts Payable | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 148 | `PAYABLES` | Payables | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 149 | `OTH_PAYABLE` | Other Payable | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 150 | `CURR_AE` | Current Accrued Expenses | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 151 | `ACCRUED_EXP` | Accrued Expenses | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 152 | `CURR_DEBT` | Current Debt | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 153 | `CURR_LEASE_LIAB` | Current Lease Obligation | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 4 |
| 154 | `CURR_DEBT_AND_LEASE` | Current Debt and Lease Obligation | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 155 | `CURR_DEF_REV` | Current Deferred Revenue | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 156 | `CURR_DEF_LIAB` | Current Deferred Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 5 |
| 157 | `CURR_DEF_TAX_LIAB` | Current Deferred Taxes Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 158 | `DEFERRED_INCOME` | Deferred Income | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 159 | `CURR_ACCRD_AND_DEF_INC` | Accrued and Deferred Income, Current | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 160 | `CURR_PROVISIONS` | Current Provisions | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 161 | `CURR_PENSION_LIAB` | Pension and Other Post Retirement Benefit Plans | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 162 | `TRADING_LIABILITIES` | Trading Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 163 | `CURR_OTH_LIAB` | Other Current Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 6 |
| 164 | `CURR_LIAB` | Total Current Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 165 | `NON_CURR_DEBT` | Long Term Debt | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 166 | `NON_CURR_LEASE_LIAB` | Long Term Lease Obligation | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 167 | `NON_CURR_DEBT_AND_LEASE` | Long Term Debt and Lease Obligation | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 168 | `NON_CURR_PROVISIONS` | Long Term Provisions | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 169 | `NON_CURR_DEF_REV` | Non-Current Deferred Revenue | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 170 | `NON_CURR_DEF_LIAB` | Non-Current Deferred Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 5 |
| 171 | `NON_CURR_DEF_TAX_LIAB` | Non-Current Deferred Taxes Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 5 |
| 172 | `NON_CURR_ACCRD_AND_DEF_INC` | Accrued and Deferred Income, Non-Current | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 173 | `NON_CURR_PENSION_AND_PRB` | Non-Current Pension and Other Post Retirement Benefit Plans | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 174 | `NON_CURR_AE` | Non-Current Accrued Expenses | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 175 | `NON_CURR_OTH_LIAB` | Other Non-Current Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 6 |
| 176 | `NON_CURR_LIAB` | Total Non-Current Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 177 | `DEBT_TOTAL` | Total Debt  | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 178 | `TOT_LEASE_OBL` | Total Lease Obligation | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 179 | `TOT_DEBT_AND_LEASE` | Total Debt and Lease Obligation | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 180 | `OTH_DEBT_AND_CASH_ITEMS` | Other Debt/(Cash)Items | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 181 | `NET_DEBT` | Net Debt | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 182 | `PROVISIONS_TOTAL` | Provisions | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 183 | `DEFERRED_TAX_LIABILITIES` | Deferred Tax Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 184 | `OTH_L` | Other Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 0 |
| 185 | `TOT_LIAB` | Total Liabilities | Balance Sheet / Assets / Liabilities and Stockholders' Equity | 8 |
| 187 | `CAPITAL_STOCK` | Share Capital | Balance Sheet / Assets / Stockholders' Equity | 6 |
| 188 | `COMMON_STOCK` | Common Stock | Balance Sheet / Assets / Stockholders' Equity | 6 |
| 189 | `PREF_STOCK` | Preferred Stock | Balance Sheet / Assets / Stockholders' Equity | 6 |
| 190 | `OTH_CAPITAL_STOCK` | Other Share Capital | Balance Sheet / Assets / Stockholders' Equity | 0 |
| 191 | `APIC` | Additional Paid-In Capital | Balance Sheet / Assets / Stockholders' Equity | 6 |
| 192 | `CAPITAL_STOCK_AND_APIC` | Share and Additional Paid-In Capital | Balance Sheet / Assets / Stockholders' Equity | 0 |
| 193 | `RETAINED_EARNINGS` | Retained Earnings | Balance Sheet / Assets / Stockholders' Equity | 6 |
| 194 | `TREASURY_STOCK` | Treasury Stock | Balance Sheet / Assets / Stockholders' Equity | 1 |
| 195 | `OTH_COMP_INC` | Other Comprehensive Income | Balance Sheet / Assets / Stockholders' Equity | 6 |
| 196 | `OTH_EI` | Other Equity Interest | Balance Sheet / Assets / Stockholders' Equity | 0 |
| 197 | `NCI_BS` | Minority Interest | Balance Sheet / Assets / Stockholders' Equity | 0 |
| 198 | `NCI_AND_PREF_STOCK` | Minority Interest and Preferred Stock | Balance Sheet / Assets / Stockholders' Equity | 0 |
| 199 | `TOT_SE` | Total Stockholders Equity | Balance Sheet / Assets / Stockholders' Equity | 8 |
| 200 | `TOT_SE_INCL_NCI` | Total Stockholders Equity including Minority Interest | Balance Sheet / Assets / Stockholders' Equity | 8 |
| 201 | `TOT_LIAB_AND_SE` | Total Liabilities and Stockholders Equity | Balance Sheet / Assets / Stockholders' Equity | 8 |
| 204 | `NET_WC` | Net Working Capital | Balance Sheet / Assets / Other Balance Sheet Items | 8 |
| 205 | `BOOK_VALUE` | Book Value | Balance Sheet / Assets / Other Balance Sheet Items | 0 |
| 206 | `BVPS` | Book Value per Share | Balance Sheet / Assets / Other Balance Sheet Items | 0 |
| 207 | `TANGIBLE_BOOK_VALUE` | Tangible Book Value | Balance Sheet / Assets / Other Balance Sheet Items | 0 |
| 208 | `TBVPS` | Tangible Book Value per Share | Balance Sheet / Assets / Other Balance Sheet Items | 0 |
| 209 | `SC_WAB` | Shares Outstanding - WAB | Balance Sheet / Assets / Other Balance Sheet Items | 0 |
| 210 | `SC_WAD` | Shares Outstanding - WAD | Balance Sheet / Assets / Other Balance Sheet Items | 0 |
| 211 | `ORDINARY_SHARES_EOP` | Total Share Count (EoP) | Balance Sheet / Assets / Other Balance Sheet Items | 0 |
| 215 | `FEDERAL_FUNDS_SOLD` | Federal Funds Sold | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 216 | `CASH_CASH_EQUIVALENTS_FEDERAL_FUNDS` | Cash and Cash Equivalents and Federal Funds Sold | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 217 | `SECURITIES_AND_INVESTMENTS` | Securities and Investments | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 218 | `SECURITY_BORROWED` | Security Borrowed | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 219 | `GROSS_LOAN` | Gross Loan | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 220 | `ALLOWANCE_FOR_LOANS_LEASE_LOSSES` | Allowance for Loans and Lease Losses | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 221 | `UNEARNED_INCOME` | Unearned Income | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 222 | `NET_LOAN` | Net Loan | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 223 | `INVESTMENTIN_FINANCIAL_ASSETS` | Investment in Financial Assets | Balance Sheet / Banking & Financial Services / Assets | 0 |
| 225 | `TOTAL_DEPOSITS` | Total Deposits | Balance Sheet / Banking & Financial Services / Liabilities | 0 |
| 226 | `INT_BEARING_DEPOSITS_LIABILITIES` | Interest Bearing Deposits Liabilities | Balance Sheet / Banking & Financial Services / Liabilities | 0 |
| 227 | `NON_INT_BEARING_DEPOSITS` | Non Interest Bearing Deposits | Balance Sheet / Banking & Financial Services / Liabilities | 0 |
| 228 | `SECURITIES_LOANED` | Securities Loaned | Balance Sheet / Banking & Financial Services / Liabilities | 0 |
| 232 | `DEFERRED_POLICY_ACQUISITION_COSTS` | Deferred Policy Acquisition Costs | Balance Sheet / Insurance / Assets | 0 |
| 233 | `REINSURANCE_ASSETS` | Reinsurance Assets | Balance Sheet / Insurance / Assets | 0 |
| 235 | `TOTAL_POLICYHOLDER_LIABILITIES` | Total Policyholder Liabilities | Balance Sheet / Insurance / Liabilities | 0 |
| 236 | `UNPAID_LOSS_RESERVE` | Unpaid Loss and Loss Reserve | Balance Sheet / Insurance / Liabilities | 0 |
| 237 | `UNEARNED_PREMIUMS` | Unearned Premiums | Balance Sheet / Insurance / Liabilities | 0 |
| 238 | `FUTURE_POLICY_BENEFITS` | Future Policy Benefits | Balance Sheet / Insurance / Liabilities | 0 |
| 239 | `POLICYHOLDER_FUNDS` | Policyholder Funds | Balance Sheet / Insurance / Liabilities | 0 |
| 240 | `INSURANCE_CONTRACT_LIABILITIES` | Insurance Contract Liabilities | Balance Sheet / Insurance / Liabilities | 0 |
| 241 | `INVESTMENT_CONTRACT_LIABILITIES` | Investment Contract Liabilities | Balance Sheet / Insurance / Liabilities | 0 |
| 242 | `REINSURANCE_BALANCES_PAYABLE` | Reinsurance Liabilities | Balance Sheet / Insurance / Liabilities | 0 |
| 245 | `OCF` | Operating Cash Flow | CASH FLOW STATEMENT | 8 |
| 246 | `CFO_BEFORE_WC` | Operating Cash Flow before WC | CASH FLOW STATEMENT | 8 |
| 247 | `NI_CONTINOP_CF` | Net Income (Loss) From Continuing Operations (CF) | CASH FLOW STATEMENT | 0 |
| 248 | `CHG_IN_WC` | Change in Working Capital | CASH FLOW STATEMENT | 8 |
| 249 | `FFO` | Funds From Operations (FFO) | CASH FLOW STATEMENT | 0 |
| 250 | `FFOPS` | Funds From Operations Per Share | CASH FLOW STATEMENT | 0 |
| 251 | `AFFO` | Adjusted Funds From Operations (FFO) | CASH FLOW STATEMENT | 0 |
| 252 | `AFFOPS` | Adjusted Funds From Operations Per Share | CASH FLOW STATEMENT | 0 |
| 253 | `DA_CF` | Depreciation and Amortization | CASH FLOW STATEMENT | 8 |
| 254 | `SBC_CF` | Stock Based Compensation | CASH FLOW STATEMENT | 8 |
| 255 | `DEF_TAX` | Deferred Tax | CASH FLOW STATEMENT | 6 |
| 256 | `NON_CASH_ADJMT_OTH` | Other Non-Cash Adjustments | CASH FLOW STATEMENT | 0 |
| 257 | `CHG_IN_WC_REC` | Change in Receivables | CASH FLOW STATEMENT | 8 |
| 258 | `CHG_IN_WC_INV` | Change in Inventories | CASH FLOW STATEMENT | 8 |
| 259 | `CHG_IN_WC_PREPAID_ASSET` | Change in Prepaid Assets | CASH FLOW STATEMENT | 5 |
| 260 | `CHG_IN_WC_PAYABLES` | Change in Payable | CASH FLOW STATEMENT | 6 |
| 261 | `CHG_IN_WC_AE` | Change in Accrued Expense | CASH FLOW STATEMENT | 5 |
| 262 | `CHG_IN_WC_OTH` | Other Changes in Working Capital | CASH FLOW STATEMENT | 6 |
| 263 | `CASH_RECEIPTS_CUSTOMER` | Receipts from Customers | CASH FLOW STATEMENT | 0 |
| 264 | `CASH_RECEIPTS_GOVT` | Receipts from Government Grants | CASH FLOW STATEMENT | 0 |
| 265 | `CASH_RECEIPTS_OTH` | Other Cash Receipts | CASH FLOW STATEMENT | 0 |
| 266 | `CASH_RECEIPTS` | Classes of Cash Receipts (Operating Activities) | CASH FLOW STATEMENT | 0 |
| 267 | `CASH_PYMT_SUPPLIERS` | Payments to Suppliers for Goods and Services | CASH FLOW STATEMENT | 0 |
| 268 | `CASH_PYMT_EE` | Payments on Behalf of Employees | CASH FLOW STATEMENT | 0 |
| 269 | `CASH_PYMT_OTH` | Other Cash Payments | CASH FLOW STATEMENT | 0 |
| 270 | `CASH_PYMT` | Classes of Cash Payments (Operating Activities) | CASH FLOW STATEMENT | 0 |
| 271 | `DIV_PAID_DIRECT` | Dividends Paid-Direct | CASH FLOW STATEMENT | 5 |
| 272 | `DIV_RECD_DIRECT` | Dividends Received-Direct | CASH FLOW STATEMENT | 0 |
| 273 | `INT_PAID_DIRECT` | Interest Paid-Direct | CASH FLOW STATEMENT | 3 |
| 274 | `INT_RECD_DIRECT` | Interest Received-Direct | CASH FLOW STATEMENT | 0 |
| 275 | `TAX_REFUND_PAID_DIRECT` | Taxes Refund Paid-Direct | CASH FLOW STATEMENT | 0 |
| 276 | `ALL_TAXES_PAID` | All Taxes Paid | CASH FLOW STATEMENT | 6 |
| 277 | `ICF` | Investing Cash Flow | CASH FLOW STATEMENT | 8 |
| 278 | `CAPEX` | Capex | CASH FLOW STATEMENT | 8 |
| 279 | `PPE_PURCH` | Purchase of PP&E | CASH FLOW STATEMENT | 5 |
| 280 | `PPE_SALE` | Sale of PP&E | CASH FLOW STATEMENT | 0 |
| 281 | `PPE_PURCH_NET` | PPE Purchase and Sale, Net | CASH FLOW STATEMENT | 0 |
| 282 | `INTANGIBLES_PURCH` | Purchase of Intangibles | CASH FLOW STATEMENT | 0 |
| 283 | `INTANGIBLES_SALE` | Sale of Intangibles | CASH FLOW STATEMENT | 0 |
| 284 | `INTANGIBLES_PURCH_NET` | Intangibles Purchase and Sale, Net | CASH FLOW STATEMENT | 0 |
| 285 | `BUSINESS_PURCH` | Acquisitons | CASH FLOW STATEMENT | 6 |
| 286 | `BUSINESS_SALE` | Divestitures | CASH FLOW STATEMENT | 0 |
| 287 | `ACQUISITIONS_NET` | Acquisitions/Divestitures, Net | CASH FLOW STATEMENT | 6 |
| 288 | `INVT_PURCH` | Purchase of Investment | CASH FLOW STATEMENT | 6 |
| 289 | `INVT_SALE` | Sale of Investment | CASH FLOW STATEMENT | 6 |
| 290 | `INVT_PURCH_NET` | Investments Purchase and Sale, Net | CASH FLOW STATEMENT | 0 |
| 291 | `OTH_ICF` | Other Investing Cash Flow | CASH FLOW STATEMENT | 4 |
| 292 | `FFCF` | Financing Cash Flow | CASH FLOW STATEMENT | 8 |
| 293 | `CHG_IN_DEBT_NET` | Increase/(Decrease) in Debt, Net | CASH FLOW STATEMENT | 0 |
| 294 | `DIV_PYMT` | Payment of Dividends | CASH FLOW STATEMENT | 0 |
| 295 | `COMMON_STOCK_ISSUED` | Common Stock Issuance, Net | CASH FLOW STATEMENT | 2 |
| 296 | `PREF_STOCK_ISSUED` | Preferred Stock Issuance, Net | CASH FLOW STATEMENT | 0 |
| 297 | `OPTIONS_EXERCISED` | Proceeds from Stock Option Exercised | CASH FLOW STATEMENT | 6 |
| 298 | `OTH_FCF` | Other Financing Cash Flow | CASH FLOW STATEMENT | 6 |
| 299 | `PROCEEDS_FROM_LOANS` | Proceeds from Loans | CASH FLOW STATEMENT | 0 |
| 300 | `PAYMENT_FOR_LOANS` | Payment for Loans | CASH FLOW STATEMENT | 0 |
| 301 | `NET_PROCEEDS_PAYMENT_FOR_LOAN` | Loan Proceeds and Payment, Net | CASH FLOW STATEMENT | 0 |
| 302 | `FCF` | Free Cash Flow | CASH FLOW STATEMENT | 8 |
| 303 | `FCFPS` | Free Cash Flow per Share | CASH FLOW STATEMENT | 5 |
| 304 | `UNLEVERED_FCF` | Unlevered FCF | CASH FLOW STATEMENT | 0 |
| 305 | `CASH_CHG` | Changes in Cash | CASH FLOW STATEMENT | 6 |
| 306 | `CASH_NET_CHG` | Increase/(decrease) in Cash and Cash Equivalents | CASH FLOW STATEMENT | 0 |
| 307 | `CASH_BOP` | Cash and Cash Equivalents - Beginning Balance | CASH FLOW STATEMENT | 8 |
| 308 | `CASH_EOP` | Cash and Cash Equivalents - Ending Balance | CASH FLOW STATEMENT | 8 |
| 309 | `FX_CASH_EFFECT` | Effect of Exchange Rate on Cash and Cash Equivalents | CASH FLOW STATEMENT | 0 |
| 310 | `OTH_CASH_ADJMT` | Other Cash Adjustments Outside Change in Cash | CASH FLOW STATEMENT | 0 |
| 311 | `CHANGE_IN_INSURANCE_LIABILITIES_NET_REINSURANCE` | Change in Insurance Liabilities Net of Reinsurance | CASH FLOW STATEMENT | 0 |
| 312 | `CHANGE_IN_INVESTMENT_CONTRACT` | Change in Investment Contract | CASH FLOW STATEMENT | 0 |
| 313 | `INT_CREDITED_POLICY_DEPOSITS` | Interest Credited on Policyholder Deposits | CASH FLOW STATEMENT | 0 |
| 314 | `CHG_LOSS_RESERVES` | Change in Loss and Loss Adjustment Expense Reserves | CASH FLOW STATEMENT | 0 |
| 315 | `CHG_UNEARNED_PREMIUMS` | Change in Unearned Premiums | CASH FLOW STATEMENT | 0 |
| 316 | `CHG_DEF_ACQ_COSTS` | Change in Deferred Acquisition Costs | CASH FLOW STATEMENT | 0 |
| 317 | `INCREASE_DECREASE_IN_DEPOSIT` | Increase/(Decrease) in Deposit | CASH FLOW STATEMENT | 0 |
| 318 | `CASH_RECEIVED_FROM_INSURANCE` | Cash Received from Insurance Activities | CASH FLOW STATEMENT | 0 |
| 319 | `CASH_RECEIPTS_TAX_REFUNDS` | Cash Receipts from Tax Refunds | CASH FLOW STATEMENT | 0 |
| 320 | `CASH_PAID_FOR_INSURANCE_ACTIVITIES` | Cash Paid for Insurance Activities | CASH FLOW STATEMENT | 0 |
| 321 | `CHANGE_IN_INSURANCE_CONTRACT_ASSETS` | Change in Insurance Contract Assets | CASH FLOW STATEMENT | 0 |
| 322 | `CHANGE_IN_REINSURANCE_RECEIVABLES` | Change in Reinsurance Receivables | CASH FLOW STATEMENT | 0 |
| 323 | `CHANGE_IN_LOANS` | Change in Loans | CASH FLOW STATEMENT | 0 |
| 324 | `CHANGE_IN_FINANCIAL_ASSETS` | Change in Financial Assets | CASH FLOW STATEMENT | 0 |
| 325 | `CHANGE_IN_DEPOSITS_BANKS_CUSTOMERS` | Change in Deposits by Banks and Customers | CASH FLOW STATEMENT | 0 |
| 326 | `CHANGE_IN_FINANCIAL_LIABILITIES` | Change in Financial Liabilities | CASH FLOW STATEMENT | 0 |
| 327 | `CASH_RECEIPTS_FROM_DEPOSITS` | Cash Receipts from Deposits by Banks and Customers | CASH FLOW STATEMENT | 0 |
| 328 | `CASH_RECEIPTS_FROM_LOANS` | Cash Receipts from Loans | CASH FLOW STATEMENT | 0 |
| 329 | `CASH_RECEIPTS_FROM_SECURITIES` | Cash Receipts from Securities Related Activities | CASH FLOW STATEMENT | 0 |
| 330 | `CASH_RECEIPTS_FROM_FEES_COMM` | Cash Receipts from Fees and Commissions | CASH FLOW STATEMENT | 0 |
| 331 | `CASH_PAYMENTS_FOR_DEPOSITS` | Cash Payments for Deposits by Banks and Customers | CASH FLOW STATEMENT | 0 |
| 332 | `CASH_PAYMENTS_FOR_LOANS` | Cash Payments for Loans | CASH FLOW STATEMENT | 0 |
| 333 | `INT_AND_COMMISSION_PAID` | Interest and Commission Paid | CASH FLOW STATEMENT | 0 |
| 334 | `OPERATING_G&L` | Operating Gains Losses | CASH FLOW STATEMENT | 0 |
| 335 | `PROVISION_FOR_LOAN_LEASE` | Provision for Loan Lease and Other Losses | CASH FLOW STATEMENT | 0 |
| 336 | `PROVISION_AND_WRITE_OFF_OF_ASSETS` | Provision and Write-Off of Assets | CASH FLOW STATEMENT | 0 |

Section header rows: 7='INCOME STATEMENT'; 79='Banking & Financial Services'; 107='Insurance'; 119='Balance Sheet'; 120='Assets'; 145="Liabilities and Stockholders' Equity"; 186="Stockholders' Equity"; 203='Other Balance Sheet Items'; 213='Banking & Financial Services'; 214='Assets'; 224='Liabilities'; 230='Insurance'; 231='Assets'; 234='Liabilities'; 244='CASH FLOW STATEMENT'.

### `Ratios` metric inventory (rows 8-150: 104 coded + 14 uncoded metric rows + 9 section headers + 16 blank rows = 143)

Uncoded metric rows (col B empty but label matches a W1 metric and is MATCH-targeted by W1 col E) are marked `(no code)`.

| Row | excel_code | Label | Section | NVDA non-null periods (of 8) |
|-----|------------|-------|---------|------------------------------|
| 8 | `GROSS_MARGIN` | Gross Margin (%) | Margins | 0 |
| 9 | `GROSS_MARGIN_ADJ` | Adj. Gross Margin, % | Margins | 0 |
| 10 | `SGA_MARGIN` | SG&A Margin (%) | Margins | 0 |
| 11 | `SGA_MARGIN_ADJ` | Adj. SG&A Margin, % | Margins | 0 |
| 12 | `RD_MARGIN` | R&D Margin (%) | Margins | 0 |
| 13 | `RD_MARGIN_ADJ` | Adj. R&D Margin, % | Margins | 0 |
| 14 | `DA_MARGIN` | D&A Margin (%) | Margins | 0 |
| 15 | `DA_MARGIN_ADJ` | Adj. D&A Margin, % | Margins | 0 |
| 16 | `SBC_MARGIN` | SBC Margin (%) | Margins | 0 |
| 17 | `EBIT_MARGIN` | EBIT Margin, % | Margins | 0 |
| 18 | `EBIT_MARGIN_ADJ` | Adj. EBIT Margin (%) | Margins | 0 |
| 19 | `EBITDA_MARGIN` | EBITDA Margin, % | Margins | 0 |
| 20 | `EBITDA_MARGIN_ADJ` | Adj. EBITDA Margin (%) | Margins | 0 |
| 21 | `TAX_RATE` | Effective Tax Rate | Margins | 0 |
| 22 | `NI_COMMON_MARGIN` | Net Income to Common Shareholders Margin, % | Margins | 0 |
| 23 | `NI_COMMON_MARGIN_ADJ` | Adj. Net Income to Common Shareholders Margin (%) | Margins | 0 |
| 24 | `FCF_NI_MARGIN` | FCF/Net Income to Common Shareholders Margin, % | Margins | 0 |
| 25 | `CAPEX_MARGIN` | CapEx Margin (%) | Margins | 0 |
| 26 | `FCF_MARGIN` | Levered FCF Margin (%) | Margins | 0 |
| 27 | `UFCF_MARGIN` | Unlevered FCF Margin (%) | Margins | 0 |
| 30 | `RECEIVABLE_TURNOVER` | Accounts Receivable Turnover | OPERATING RATIOS | 0 |
| 31 | `DSO` | Days Sales Outstanding (DSO) | OPERATING RATIOS | 0 |
| 32 | `INVENTORY_TURNOVER` | Inventory Turnover | OPERATING RATIOS | 0 |
| 33 | `DIO` | Days Inventory Outstanding (DIO) | OPERATING RATIOS | 0 |
| 34 | `PAYABLE_TURNOVER` | Accounts Payable Turnover | OPERATING RATIOS | 0 |
| 35 | `DPO` | Days Payable Outstanding (DPO) | OPERATING RATIOS | 0 |
| 36 | `CCC` | Cash Conversion Cycle (CCC) | OPERATING RATIOS | 0 |
| 37 | `FIXED_ASSET_TURNOVER` | Fixed Asset Turnover | OPERATING RATIOS | 0 |
| 38 | `TOTAL_ASSET_TURNOVER` | Total Asset Turnover | OPERATING RATIOS | 0 |
| 41 | `CURRENT_RATIO` | Current Ratio | LIQUIDITY RATIOS | 0 |
| 42 | `QUICK_RATIO` | Quick Ratio | LIQUIDITY RATIOS | 0 |
| 43 | `CASH_RATIO` | Cash Ratio | LIQUIDITY RATIOS | 0 |
| 46 | `EBIT_TO_INT_EXP` | EBIT/Interest Expenses | COVERAGE RATIOS | 0 |
| 47 | `EBITDA_TO_INT_EXP` | EBITDA/Interest Expenses | COVERAGE RATIOS | 0 |
| 48 | `EBITDA_LESS_CAPEX_TO_INT_EXP` | (EBITDA-CapEx)/Interest Expenses | COVERAGE RATIOS | 0 |
| 49 | `DEBT_TO_EBITDA` | Total Debt/EBITDA | COVERAGE RATIOS | 0 |
| 50 | `NET_DEBT_TO_EBITDA` | Net Debt/EBITDA | COVERAGE RATIOS | 0 |
| 51 | `TOT_DEBT_TO_OCF` | Total Debt/Operating Cash Flow | COVERAGE RATIOS | 0 |
| 52 | `TOT_DEBT_TO_EBITDA_LESS_CAPEX` | Total Debt/(EBITDA-CapEx) | COVERAGE RATIOS | 0 |
| 53 | `NET_DEBT_TO_OCF` | Net Debt/Operating Cash Flow | COVERAGE RATIOS | 0 |
| 54 | `UFCF_TO_TOT_DEBT` | Unlevered FCF/Total Debt | COVERAGE RATIOS | 0 |
| 55 | `NET_DEBT_TO_EBITDA_LESS_CAPEX` | Net Debt/(EBITDA-CapEx) | COVERAGE RATIOS | 0 |
| 58 | `TOT_ASSET_TO_EQUITY` | Total Assets/Shareholders' Equity | LEVERAGE & SOLVENCY RATIOS | 0 |
| 59 | `TOT_DEBT_TO_EQUITY` | Total Debt/Shareholders' Equity | LEVERAGE & SOLVENCY RATIOS | 0 |
| 60 | `TOT_DEBT_TO_CAPITAL` | Total Debt/Total Capital | LEVERAGE & SOLVENCY RATIOS | 0 |
| 61 | `LT_DEBT_TO_EQUITY` | LT Debt/Equity | LEVERAGE & SOLVENCY RATIOS | 0 |
| 62 | `LT_DEBT_TO_CAPITAL` | LT Debt/Total Capital | LEVERAGE & SOLVENCY RATIOS | 0 |
| 63 | `LT_DEBT_TO_ASSET` | LT Debt/Total Assets | LEVERAGE & SOLVENCY RATIOS | 0 |
| 64 | `TOT_DEBT_TO_ASSET` | Total Debt/Total Assets | LEVERAGE & SOLVENCY RATIOS | 0 |
| 65 | `TOT_ASSET_TO_EQUITY` | Total Assets/Shareholders' Equity | LEVERAGE & SOLVENCY RATIOS | 0 |
| 66 | `TOT_LIAB_TO_ASSET` | Total Liabilities/Total Assets | LEVERAGE & SOLVENCY RATIOS | 0 |
| 69 | `CAPEX_TO_DA` | CapEx/D&A | CAPITAL INTENSITY RATIOS | 0 |
| 70 | `CAPEX_TO_PPE` | Capex/PP&E | CAPITAL INTENSITY RATIOS | 0 |
| 71 | `DA_TO_PPE` | D&A/PP&E | CAPITAL INTENSITY RATIOS | 0 |
| 72 | `FIXED_ASSET_TURNOVER` | Fixed Asset Turnover | CAPITAL INTENSITY RATIOS | 0 |
| 73 | `TOTAL_ASSET_TURNOVER` | Total Asset Turnover | CAPITAL INTENSITY RATIOS | 0 |
| 74 | `NWC_TO_AVG_ASSET` | Net Working Capital/Average Assets | CAPITAL INTENSITY RATIOS | 0 |
| 77 | `DIV_YIELD` | Dividend Yield (%) | DIVIDEND SUMMARY | 0 |
| 78 | `DIV_PAYOUT_RATIO` | Dividend Payout Ratio, % | DIVIDEND SUMMARY | 0 |
| 79 | `LTM_DIV_PAYOUT_RATIO` | LTM Dividend Payout Ratio (%) | DIVIDEND SUMMARY | 0 |
| 82 | `TIER1_COMM_EQUITY_RATIO` | Common Equity Tier 1 Ratio, % | DIVIDEND SUMMARY | 0 |
| 83 | `TIER1_CAPITAL_RATIO` | Tier 1 Capital Ratio, % | DIVIDEND SUMMARY | 0 |
| 84 | `TIER2_CAPITAL_RATIO` | Tier 2 Capital Ratio, % | DIVIDEND SUMMARY | 0 |
| 85 | `NET_INT_MARGIN` | Net Interest Margin, % | DIVIDEND SUMMARY | 0 |
| 86 | `COST_TO_INC_RATIO` | Cost to Income Ratio, % | DIVIDEND SUMMARY | 0 |
| 87 | `EFFICIENCY_RATIO` | Efficiency Ratio, % | DIVIDEND SUMMARY | 0 |
| 90 | `ROE` | Return on Equity | PROFITABILITY RATIOS | 0 |
| 91 | `ROIC` | Return on Invested Capital | PROFITABILITY RATIOS | 0 |
| 92 | `ROA` | Return on Assets | PROFITABILITY RATIOS | 0 |
| 93 | `ROCE` | Return on Capital Employed | PROFITABILITY RATIOS | 0 |
| 96 | `LOSS_RATIO` | Loss Ratio, % | PROFITABILITY RATIOS | 0 |
| 97 | `EXPENSE_RATIO` | Expense Ratio, % | PROFITABILITY RATIOS | 0 |
| 98 | `COMBINED_RATIO` | Combined Ratio, % | PROFITABILITY RATIOS | 0 |
| 101 | `CREDIT_LOSSES_PROV_MARGIN` | Provision for Credit Losses Margin, % | PROFITABILITY RATIOS | 0 |
| 102 | `COMPENSATION_EXPENSE_MARGIN` | Compensation Expense Margin, % | PROFITABILITY RATIOS | 0 |
| 103 | `OCCUPANCY_EQUIPMENT_MARGIN` | Occupancy and Equipment Expense Margin, % | PROFITABILITY RATIOS | 0 |
| 104 | `PROFESSIONAL_EXPENSES_MARGIN` | Professional Expenses Margin, % | PROFITABILITY RATIOS | 0 |
| 107 | (no code) | Reserves to Surplus Ratio, % | PROFITABILITY RATIOS | 0 |
| 108 | (no code) | Loan to Assets Ratio, % | PROFITABILITY RATIOS | 0 |
| 109 | (no code) | Loan to Deposit Ratio, % | PROFITABILITY RATIOS | 0 |
| 112 | `PE` | P/E | VALUATION MULTIPLES | 8 |
| 113 | `PE_ADJ` | Adj. P/E | VALUATION MULTIPLES | 8 |
| 114 | `P_TO_SALES` | P/Sales | VALUATION MULTIPLES | 8 |
| 115 | `P_TO_SALES_ADJ` | P/Adj. Sales | VALUATION MULTIPLES | 0 |
| 116 | `P_TO_BV` | P/BV | VALUATION MULTIPLES | 0 |
| 117 | `P_TO_TBV` | P/TBV | VALUATION MULTIPLES | 0 |
| 118 | `P_TO_CF` | P/CashFlow | VALUATION MULTIPLES | 8 |
| 119 | `P_TO_FCF` | P/FCF | VALUATION MULTIPLES | 8 |
| 120 | `P_TO_FFO` | P/AFFO | VALUATION MULTIPLES | 0 |
| 121 | `EV_TO_SALES` | EV/Sales | VALUATION MULTIPLES | 8 |
| 122 | `EV_TO_SALES_ADJ` | EV/Adj. Sales | VALUATION MULTIPLES | 0 |
| 123 | `EV_TO_GP` | EV/Gross Profit | VALUATION MULTIPLES | 6 |
| 124 | `EV_TO_GP_ADJ` | EV/Adj. Gross Profit | VALUATION MULTIPLES | 8 |
| 125 | `EV_TO_EBITDA` | EV/EBITDA | VALUATION MULTIPLES | 8 |
| 126 | `EV_TO_EBITDA_ADJ` | EV/Adj. EBITDA | VALUATION MULTIPLES | 8 |
| 127 | `EV_TO_EBIT` | EV/EBIT | VALUATION MULTIPLES | 8 |
| 128 | `EV_TO_EBIT_ADJ` | EV/Adj. EBIT | VALUATION MULTIPLES | 8 |
| 129 | `EV_TO_FCF` | EV/FCF | VALUATION MULTIPLES | 8 |
| 130 | (no code) | EV/(EBITDA-CapEx) | VALUATION MULTIPLES | 0 |
| 131 | (no code) | Adj. EV/(EBITDA-CapEx) | VALUATION MULTIPLES | 0 |
| 132 | `FCF_YIELD_MCAP` | FCF Yield (based on Market Cap) | VALUATION MULTIPLES | 8 |
| 133 | (no code) | Unlevered FCF Yield, % | VALUATION MULTIPLES | 0 |
| 134 | (no code) | PEG | VALUATION MULTIPLES | 0 |
| 135 | `NET_DEBT_TO_EV` | Net Debt/EV | VALUATION MULTIPLES | 8 |
| 136 | `TOT_DEBT_TO_EV` | Total Debt/EV | VALUATION MULTIPLES | 8 |
| 137 | `P_TO_FFO` | P/FFO | VALUATION MULTIPLES | 0 |
| 138 | `MCAP` | Market Capitalization | VALUATION MULTIPLES | 6 |
| 139 | `EV` | Enterprise Value | VALUATION MULTIPLES | 6 |
| 140 | (no code) | Total Shares Outstanding (EoP Basic) | VALUATION MULTIPLES | 0 |
| 141 | (no code) | Shares per Listing | VALUATION MULTIPLES | 0 |
| 142 | (no code) | Enterprise Value per Share | VALUATION MULTIPLES | 0 |
| 143 | (no code) | Stock Price (End Of Day) | VALUATION MULTIPLES | 0 |
| 144 | `OPEN` | Stock Price-Open | VALUATION MULTIPLES | 6 |
| 145 | `HIGH` | Stock Price-High | VALUATION MULTIPLES | 6 |
| 146 | `LOW` | Stock Price-Low | VALUATION MULTIPLES | 6 |
| 147 | (no code) | Last Traded Price | VALUATION MULTIPLES | 0 |
| 148 | (no code) | Last Transaction Volume | VALUATION MULTIPLES | 0 |
| 149 | (no code) | Last Trade Date Time | VALUATION MULTIPLES | 0 |

Data-quality notes: duplicate codes on the Ratios tab: `FIXED_ASSET_TURNOVER`, `TOTAL_ASSET_TURNOVER`, `TOT_ASSET_TO_EQUITY`, `P_TO_FFO` each appear twice; row 120 pairs code `P_TO_FFO` with label `P/AFFO` while W1's consensus sheet maps `P/AFFO`→`P_TO_AFFO` (label/code mismatch). Ratios B1 holds a stray `0`; C1:K1 is the sheet's only merged range (title).

## Sheet `Trading Multiples` — all 54 columns (A..BB)

Dated daily panel. Structure: cols A-B empty; then **26 (Date, Value) column pairs** (C..BB). Header rows: row 7 = display name, row 8 = excel_code, row 9 = query caption `"NVDA - <metric> (2025-01-01, 2026-06-21)"` repeating the ticker and the user-set date window. Data rows start at row 10. Sheet extends to row 1678 but data ends at row 384; rows 385-1678 are empty padding.

| Col | Row-7 header | Row-8 code | Type | Obs | First date | Last date | Example value (first row) |
|-----|--------------|------------|------|-----|------------|-----------|----------------------------|
| A | (empty) | | empty | 0 | | | |
| B | (empty) | | empty | 0 | | | |
| C | Date |  | date (ISO day) | 375 | 2025-01-02 | 2026-06-18 | |
| D | Share Price | `CLOSE` | float (value) | 375 | | | 138.31 |
| E | (date of pair to the right) |  | date (ISO day) | 375 | 2025-01-02 | 2026-06-18 | |
| F | Market Capitalization | `MCAP` | float (value) | 375 | | | 3387211.9 |
| G | (date of pair to the right) |  | date (ISO day) | 375 | 2025-01-02 | 2026-06-18 | |
| H | Enterprise Value | `EV` | float (value) | 375 | | | 3358676.9 |
| I | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| J | P/E LTM | `PE` | float (value) | 254 | | | 54.452755905511815 |
| K | (date of pair to the right) |  | date (ISO day) | 375 | 2025-01-02 | 2026-06-18 | |
| L | Adj. P/E LTM | `PE_ADJ` | float (value) | 375 | | | 52.835131413568384 |
| M | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| N | P/Sales LTM | `P_TO_SALES` | float (value) | 254 | | | 29.904138819977224 |
| O | (date of pair to the right) |  | date (ISO day) | 0 | (empty) |  | |
| P | P/Adj. Sales LTM | `P_TO_SALES_ADJ` | float (value) | 0 | | | (empty) |
| Q | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| R | EV/Sales LTM | `EV_TO_SALES` | float (value) | 254 | | | 29.652216405194714 |
| S | (date of pair to the right) |  | date (ISO day) | 0 | (empty) |  | |
| T | EV/Adj. Sales LTM | `EV_TO_SALES_ADJ` | float (value) | 0 | | | (empty) |
| U | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| V | EV/Gross Profit LTM | `EV_TO_GP` | float (value) | 254 | | | 39.08756153479116 |
| W | (date of pair to the right) |  | date (ISO day) | 375 | 2025-01-02 | 2026-06-18 | |
| X | EV/Adj. Gross Profit LTM | `EV_TO_GP_ADJ` | float (value) | 375 | | | 38.79723807323553 |
| Y | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| Z | EV/EBITDA LTM | `EV_TO_EBITDA` | float (value) | 254 | | | 46.17182271833716 |
| AA | (date of pair to the right) |  | date (ISO day) | 375 | 2025-01-02 | 2026-06-18 | |
| AB | EV/Adj. EBITDA LTM | `EV_TO_EBITDA_ADJ` | float (value) | 375 | | | 43.21008761208815 |
| AC | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AD | EV/EBIT LTM | `EV_TO_EBIT` | float (value) | 254 | | | 47.28200042232702 |
| AE | (date of pair to the right) |  | date (ISO day) | 375 | 2025-01-02 | 2026-06-18 | |
| AF | EV/Adj. EBIT LTM | `EV_TO_EBIT_ADJ` | float (value) | 375 | | | 44.18090922245169 |
| AG | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AH | P/Cashflow LTM | `P_TO_CF` | float (value) | 254 | | | 57.45029427229091 |
| AI | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AJ | P/FCF LTM | `P_TO_FCF` | float (value) | 254 | | | 59.90082409323218 |
| AK | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AL | EV/FCF LTM | `EV_TO_FCF` | float (value) | 254 | | | 59.39619962155375 |
| AM | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AN | FCF Yield (based on Market Cap) LTM | `FCF_YIELD_MCAP` | float (value) | 254 | | | 0.016694261141442023 |
| AO | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AP | Net Debt/EV LTM | `NET_DEBT_TO_EV` | float (value) | 254 | | | -0.005755659319299215 |
| AQ | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AR | Total Debt/EV LTM  | `TOT_DEBT_TO_EV` | float (value) | 254 | | | 0.0031162866544263306 |
| AS | (date of pair to the right) |  | date (ISO day) | 0 | (empty) |  | |
| AT | P/BV LTM | `P_TO_BV` | float (value) | 0 | | | (empty) |
| AU | (date of pair to the right) |  | date (ISO day) | 0 | (empty) |  | |
| AV | P/TBV LTM | `P_TO_TBV` | float (value) | 0 | | | (empty) |
| AW | (date of pair to the right) |  | date (ISO day) | 254 | 2025-01-02 | 2026-06-18 | |
| AX | P/FCF LTM | `P_TO_FCF` | float (value) | 254 | | | 59.90082409323218 |
| AY | (date of pair to the right) |  | date (ISO day) | 0 | (empty) |  | |
| AZ | P/AFFO LTM | `P_TO_AFFO` | float (value) | 0 | | | (empty) |
| BA | (date of pair to the right) |  | date (ISO day) | 0 | (empty) |  | |
| BB | PEG LTM | `PEG` | float (value) | 0 | | | (empty) |

### Pair-level summary (26 pairs)

| Pair (date,value) | Metric (row 7) | Code | Obs | Date span | Notes |
|-------------------|----------------|------|-----|-----------|-------|
| C,D | Share Price | `CLOSE` | 375 | 2025-01-02 .. 2026-06-18 |  |
| E,F | Market Capitalization | `MCAP` | 375 | 2025-01-02 .. 2026-06-18 |  |
| G,H | Enterprise Value | `EV` | 375 | 2025-01-02 .. 2026-06-18 |  |
| I,J | P/E LTM | `PE` | 254 | 2025-01-02 .. 2026-06-18 |  |
| K,L | Adj. P/E LTM | `PE_ADJ` | 375 | 2025-01-02 .. 2026-06-18 |  |
| M,N | P/Sales LTM | `P_TO_SALES` | 254 | 2025-01-02 .. 2026-06-18 |  |
| O,P | P/Adj. Sales LTM | `P_TO_SALES_ADJ` | 0 |  ..  | EMPTY — header only, no data returned for NVDA |
| Q,R | EV/Sales LTM | `EV_TO_SALES` | 254 | 2025-01-02 .. 2026-06-18 |  |
| S,T | EV/Adj. Sales LTM | `EV_TO_SALES_ADJ` | 0 |  ..  | EMPTY — header only, no data returned for NVDA |
| U,V | EV/Gross Profit LTM | `EV_TO_GP` | 254 | 2025-01-02 .. 2026-06-18 |  |
| W,X | EV/Adj. Gross Profit LTM | `EV_TO_GP_ADJ` | 375 | 2025-01-02 .. 2026-06-18 |  |
| Y,Z | EV/EBITDA LTM | `EV_TO_EBITDA` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AA,AB | EV/Adj. EBITDA LTM | `EV_TO_EBITDA_ADJ` | 375 | 2025-01-02 .. 2026-06-18 |  |
| AC,AD | EV/EBIT LTM | `EV_TO_EBIT` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AE,AF | EV/Adj. EBIT LTM | `EV_TO_EBIT_ADJ` | 375 | 2025-01-02 .. 2026-06-18 |  |
| AG,AH | P/Cashflow LTM | `P_TO_CF` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AI,AJ | P/FCF LTM | `P_TO_FCF` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AK,AL | EV/FCF LTM | `EV_TO_FCF` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AM,AN | FCF Yield (based on Market Cap) LTM | `FCF_YIELD_MCAP` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AO,AP | Net Debt/EV LTM | `NET_DEBT_TO_EV` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AQ,AR | Total Debt/EV LTM | `TOT_DEBT_TO_EV` | 254 | 2025-01-02 .. 2026-06-18 |  |
| AS,AT | P/BV LTM | `P_TO_BV` | 0 |  ..  | EMPTY — header only, no data returned for NVDA |
| AU,AV | P/TBV LTM | `P_TO_TBV` | 0 |  ..  | EMPTY — header only, no data returned for NVDA |
| AW,AX | P/FCF LTM | `P_TO_FCF` | 254 | 2025-01-02 .. 2026-06-18 | duplicate pair — verified cell-identical to pair AI,AJ (`P_TO_FCF` queried twice) |
| AY,AZ | P/AFFO LTM | `P_TO_AFFO` | 0 |  ..  | EMPTY — header only, no data returned for NVDA |
| BA,BB | PEG LTM | `PEG` | 0 |  ..  | EMPTY — header only, no data returned for NVDA |

Observations:
- Date semantics: exchange trading days (Mon-Fri minus US holidays), ISO dates, ascending; window = user-set 2025-01-01..2026-06-21, data through 2026-06-18 (last trading day before the end date at save time).
- Two observation counts: 375 obs (full daily series: `CLOSE`, `MCAP`, `EV`, and the `_ADJ` multiples) vs 254 obs (unadjusted LTM multiples).
- The 254-obs series have two ~3-month holes: 2025-07-30 -> 2025-10-26 and 2026-01-30 -> 2026-04-26 — daily values disappear until the next quarter's LTM fundamentals become available, then resume. Each pair carries its own date column because series lengths differ.
- 6 pairs returned no data for NVDA: `P_TO_SALES_ADJ`, `EV_TO_SALES_ADJ`, `P_TO_BV`, `P_TO_TBV`, `P_TO_AFFO`, `PEG` (headers present, values empty).
- Distinct codes: 25 (26 code-bearing pairs - 1 duplicated `P_TO_FCF` = 25). 22 of the 25 also appear as codes on the Ratios tab; the 3 exceptions are `CLOSE` (coded only on Front Page r17 and here, not a Ratios code), `PEG` (label-only Ratios row 134 with no code; the name exists in W1 Financial Metrics r414 / Available Consensus r168), and `P_TO_AFFO` (appears only in W1 Available Consensus r167 and this TM header; the Ratios tab pairs the `P/AFFO` label with code `P_TO_FFO`, r120).
- Units: prices in trading currency (USD); `MCAP`/`EV` in millions; multiples dimensionless; `FCF_YIELD_MCAP` decimal fraction (0.0167 = 1.67%).

## Sheet `Data` (lookup/config sheet)

Small lookup grid backing the Front Page dropdowns (sheet_state = visible, i.e. not hidden in this copy).

| Cell(s) | Content |
|---------|---------|
| A1:B1 | `Selected Currency Code` = `USD`, via `=VLOOKUP('Front Page'!$D$4,Data!$A$2:$B$4,2,0)` |
| D1:E1 | `Selceted Period Type` [sic] = `FY`, via `=VLOOKUP('Front Page'!$D$5,Data!$D$3:$E$5,2,0)` |
| A2:B4 | Currency list: `Reporting Currency`->`USD` (NVDA), `US Dollar (USD)`->`USD` |
| D2:E5 | Period types: `Fiscal Year`->`FY`, `Fiscal Quarter`->`FQ`, `Fiscal Semi-Annual`->`FH` |
| N2:O3 | **`Version Type`: `Latest restatement` -> `latest_filing`** — the template's only data-version option |

