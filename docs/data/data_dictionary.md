# Canonical data dictionary — AlphaSense workbooks (G012)

Sources: W1 `AlphaSense Financial Data Available Metrics with Consensus_v3.xlsx` (SHA-256 `9bf1cdeb4bfbaa92...`), W2 `ASQ_Comprehensive_Financial_Data_NVDA_v3.xlsx` (SHA-256 `40973092c8a3f598...`).
Full structural catalogs with per-sheet citations: `docs/data/workbook_schema/`. PIT caveats: `docs/data/pit_assessment.md` (assumption A-001 applies to every row here: presence != point-in-time access).

## Conventions

- `excel_code`: provider mnemonic. Precedence when present in multiple sources: W1 `Available Consensus` col B, else W2 sheet code (Front Page / Financial Statements / Ratios / Trading Multiples). Conflicts are footnoted.
- `frequency`: W1 `Financial Metrics` col C verbatim (`Q` quarterly-reported fundamental, `D/M` daily/monthly market, `M` monthly, `W` weekly, `LTM` trailing-twelve-month, `N/A` static). NOT a delivery-latency claim.
- `consensus`: `Y` iff W1 col B = `Yes` (metric present in the `Available Consensus` sheet).
- `tabs`: which W2 template tab carries the field — FS = Financial Statements (row), RA = Ratios (row), FP = Front Page (row), TM = Trading Multiples (value column).
- `units`: inferred from label suffixes (`, %`, `(Usd, Mn)`, `(Th)`, `(in mm)`), per-share naming, and NVDA example magnitudes (money statement items are millions of the selected currency — Data!A1:B1 currency selector); `NOT_ESTABLISHED` where no signal exists in the workbooks.
- `nullability (NVDA)`: observed fill in W2's single NVDA example — `k/8` = non-null relative-period columns on FS/RA; `v`/`empty` on FP; `n=NNN` TM daily observations; `n/a` = field not in W2 at all. One company, one snapshot: NOT a general availability statement.

## Section 1 — Equity metrics (W1 `Financial Metrics` col A: 513 rows, 508 distinct names)

Keyed by W1 row so the count reconciles exactly with the sheet (513 rows); the 5 duplicated names are flagged `dup`.

| W1 row | name | excel_code | category | freq | cons | tabs | units | nullability (NVDA) |
|--------|------|------------|----------|------|------|------|-------|--------------------|
| 2 | Revenue | `REV` | Income Statement | Q | Y | FS r8 | mn, selected ccy | 8/8 |
| 3 | Cost of Goods Sold | `COGS` | Fundamentals | Q |  | FS r15 | mn, selected ccy | 6/8 |
| 4 | Gross Profit | `GP` | Fundamentals | Q |  | FS r18 | mn, selected ccy | 6/8 |
| 5 | EBIT | `EBIT` | Income Statement | Q | Y | FS r47 | mn, selected ccy | 8/8 |
| 6 | Revenue Adjustments | `REV_ADJMT` | Fundamentals | Q |  | FS r9 | mn, selected ccy | 0/8 |
| 7 | Adj. Revenue | `REV_ADJ` | Income Statement | Q | Y | FS r10 | mn, selected ccy | 0/8 |
| 8 | Selling and Marketing Expense | `SM_EXP` | Fundamentals | Q |  | FS r22 | mn, selected ccy | 0/8 |
| 9 | General and Administrative Expense | `GA_EXP` | Fundamentals | Q |  | FS r23 | mn, selected ccy | 0/8 |
| 10 | Staff Costs | `STAFF_COSTS` | Fundamentals | Q |  | FS r24 | mn, selected ccy | 0/8 |
| 11 | Selling, General and Administrative Expense | `SGA_EXP` | Fundamentals | Q |  | FS r21 | mn, selected ccy | 8/8 |
| 12 | Research and Development Expense | `RD_EXP` | Fundamentals | Q |  | FS r31 | mn, selected ccy | 8/8 |
| 13 | Depreciation and Amortization Expense | `DA_EXP_OP` | Fundamentals | Q |  | FS r42 | mn, selected ccy | 0/8 |
| 14 | Other Operating Expenses | `OP_EXP_OTH` | Fundamentals | Q |  | FS r34 | mn, selected ccy | 5/8 |
| 15 | EBIT Adjustments | `EBIT_ADJMT` | Fundamentals | Q |  | FS r48 | mn, selected ccy | 0/8 |
| 16 | Adj. EBIT | `EBIT_ADJ` | Income Statement | Q | Y | FS r49 | mn, selected ccy | 8/8 |
| 17 | EBITDA | `EBITDA` | Income Statement | Q | Y | FS r38 | mn, selected ccy | 8/8 |
| 18 | Adj. EBITDA | `EBITDA_ADJ` | Income Statement | Q | Y | FS r41 | mn, selected ccy | 8/8 |
| 19 | Interest Income | `INT_INC` | Fundamentals | Q |  | FS r81 | mn, selected ccy | 6/8 |
| 20 | Interest Expense | `INT_EXP` | Fundamentals | Q |  | FS r95 | mn, selected ccy | 6/8 |
| 21 | Interest Income (Expense), Net | `INT_INC_NET` | Fundamentals | Q |  | FS r102 | mn, selected ccy | 8/8 |
| 22 | Other Non-Operating Income (Expense), Net | `NON_OP_INC_OTH` | Fundamentals | Q |  | FS r51 | mn, selected ccy | 6/8 |
| 23 | EBT | `EBT` | Fundamentals | Q |  | FS r55 | mn, selected ccy | 8/8 |
| 24 | Tax Expense | `TAX_EXP` | Fundamentals | Q |  | FS r58 | mn, selected ccy | 8/8 |
| 25 | Earnings from Equity Interest Net of Tax | `EQUITY_INCOME_POST_TAX` | Fundamentals | Q |  | FS r66 | mn, selected ccy | 0/8 |
| 26 | Net Income from Continuous Operations | `NI_CONTINOP` | Fundamentals | Q |  | FS r62 | mn, selected ccy | 6/8 |
| 27 | Net Income Discontinuous Operations | `NI_DISCONT` | Fundamentals | Q |  | FS r63 | mn, selected ccy | 0/8 |
| 28 | Net Income Extraordinary | `NI_EXTRAORDINARY` | Fundamentals | Q |  | FS r64 | mn, selected ccy | 0/8 |
| 29 | Net Income from Tax Loss Carry Forward | `NI_TAX_LOSS` | Fundamentals | Q |  | FS r65 | mn, selected ccy | 0/8 |
| 30 | Net Income to NCI | `NI_NCI` | Fundamentals | Q |  | FS r67 | mn, selected ccy | 0/8 |
| 31 | Preferred Stock Dividends and Other | `PREF_STOCK_DIV_AND_OTH` | Fundamentals | Q |  | FS r68 | mn, selected ccy | 0/8 |
| 32 | Net Income to Common Shareholders | `NI_BASIC` | Income Statement | Q | Y | FS r69 | mn, selected ccy | 8/8 |
| 33 | Net Income to Common Shareholder Adjustments | `NI_BASIC_ADJMT` | Fundamentals | Q |  | FS r70 | mn, selected ccy | 0/8 |
| 34 | Adj. Net Income to Common Shareholders | `NI_BASIC_ADJ` | Income Statement | Q | Y | FS r71 | mn, selected ccy | 8/8 |
| 35 | Adjustments for Convertible Securities | `NI_DILUTION` | Fundamentals | Q |  | FS r72 | mn, selected ccy | 0/8 |
| 36 | Diluted Net Income to Common Shareholders | `NI_DILUTED` | Fundamentals | Q |  | FS r73 | mn, selected ccy | 8/8 |
| 37 | Earnings Per Share - WAB | `EPS_WAB` | Fundamentals | Q |  | FS r74 | ccy/share | 6/8 |
| 38 | Earnings Per Share - WAD | `EPS_WAD` | Income Statement | Q | Y | FS r75 | ccy/share | 8/8 |
| 39 | Adj. Earnings Per Share - WAD | `EPS_WAD_ADJ` | Income Statement | Q | Y | FS r76 | ccy/share | 8/8 |
| 40 | Shares Outstanding - WAB | `SC_WAB` | Fundamentals | Q |  | FS r209 | mn, selected ccy | 0/8 |
| 41 | Shares Outstanding - WAD | `SC_WAD` | Fundamentals | Q |  | FS r210 | mn, selected ccy | 0/8 |
| 42 | Dividends Per Share | `DPS` | Income Statement | Q | Y | FS r77 | ccy/share | 7/8 |
| 43 | Gross Profit Adjustments | `GP_ADJMT` | Fundamentals | Q |  | FS r19 | mn, selected ccy | 0/8 |
| 44 | Adj. Gross Profit | `GP_ADJ` | Income Statement | Q | Y | FS r20 | mn, selected ccy | 8/8 |
| 45 | Depreciation | `DEP` | Fundamentals | Q |  | FS r43 | mn, selected ccy | 0/8 |
| 46 | Amortization | `AMORT` | Fundamentals | Q |  | FS r44 | mn, selected ccy | 0/8 |
| 47 | Add Back: D&A | NOT_ESTABLISHED | Fundamentals | Q |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 48 | EBITDA Adjustments | `EBITDA_ADJMT` | Fundamentals | Q |  | FS r39 | mn, selected ccy | 0/8 |
| 49 | Cost of Goods Sold Adjustments | `COGS_ADJMT` | Fundamentals | Q |  | FS r16 | mn, selected ccy | 0/8 |
| 50 | Adj. Cost of Goods Sold | `COGS_ADJ` | Income Statement | Q | Y | FS r17 | mn, selected ccy | 0/8 |
| 51 | Selling, General and Administrative Expense Adjustments | `SGA_EXP_ADJMT` | Fundamentals | Q |  | FS r29 | mn, selected ccy | 0/8 |
| 52 | Adj. Selling, General and Administrative Expense | `SGA_EXP_ADJ` | Income Statement | Q | Y | FS r30 | mn, selected ccy | 0/8 |
| 53 | Research and Development Expense Adjustments | `RD_EXP_ADJMT` | Fundamentals | Q |  | FS r32 | mn, selected ccy | 0/8 |
| 54 | Adj. Research and Development Expense | `RD_EXP_ADJ` | Income Statement | Q | Y | FS r33 | mn, selected ccy | 0/8 |
| 55 | Depreciation and Amortization Expense Adjustments | `DA_EXP_OP_ADJMT` | Fundamentals | Q |  | FS r45 | mn, selected ccy | 0/8 |
| 56 | Adj. Depreciation and Amortization Expense | `DA_EXP_OP_ADJ` | Income Statement | Q | Y | FS r46 | mn, selected ccy | 0/8 |
| 57 | Other Operating Adjustments | `OP_EXP_OTH_ADJMT` | Fundamentals | Q |  | FS r35 | mn, selected ccy | 0/8 |
| 58 | Other Adjustments to EBITDA | `OTH_EBITDA_ADJMT` | Fundamentals | Q |  | FS r40 | mn, selected ccy | 0/8 |
| 59 | Interest Income (Expense), Net Adjustments | `INT_INC_NET_ADJMT` | Fundamentals | Q |  | FS r103 | mn, selected ccy | 0/8 |
| 60 | Adj. Interest Income (Expense), Net | `INT_INC_NET_ADJ` | Income Statement | Q | Y | FS r104 | mn, selected ccy | 0/8 |
| 61 | Other Non-Operating Adjustments | `OTHER_NON_OP_ADJMT` | Fundamentals | Q |  | FS r52 | mn, selected ccy | 0/8 |
| 62 | EBT Adjustments | `EBT_ADJMT` | Fundamentals | Q |  | FS r56 | mn, selected ccy | 0/8 |
| 63 | Adj. EBT | `EBT_ADJ` | Income Statement | Q | Y | FS r57 | mn, selected ccy | 0/8 |
| 64 | Tax Expense Adjustments | `TAX_EXP_ADJMT` | Fundamentals | Q |  | FS r59 | mn, selected ccy | 0/8 |
| 65 | Adj. Tax Expense | `TAX_EXP_ADJ` | Income Statement | Q | Y | FS r60 | mn, selected ccy | 0/8 |
| 66 | Effective Tax Rate_2 | `TAX_RATE_2` | Income Statement | Q | Y | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 67 | Funds From Operations (FFO) | `FFO` | Income Statement | Q | Y | FS r249 | mn, selected ccy | 0/8 |
| 68 | Funds From Operations Per Share | `FFOPS` | Income Statement | Q | Y | FS r250 | ccy/share | 0/8 |
| 69 | Net Premiums Written | `NET_PREMIUMS_WRITTEN` | Income Statement | Q | Y | FS r110 | mn, selected ccy | 0/8 |
| 70 | Change in Net Unearned Premium Reserves | `NET_UNEARNED_PREMIUM` | Fundamentals | Q |  | FS r111 | mn, selected ccy | 0/8 |
| 71 | Net Earned Premiums | `NET_EARNED_PREMIUMS` | Income Statement | Q | Y | FS r112 | mn, selected ccy | 0/8 |
| 72 | Net Investment Income | `NET_INVESTMENT_INCOME` | Fundamentals | Q |  | FS r92 | mn, selected ccy | 0/8 |
| 73 | Net Investment Gains | `NET_INVESTMENT_GAINS` | Fundamentals | Q |  | FS r93 | mn, selected ccy | 0/8 |
| 74 | Interest Revenue | `INT_REVENUE` | Fundamentals | Q |  | FS r80 | mn, selected ccy | 0/8 |
| 75 | Net Foreign Exchange Gain/Loss | `NET_FOREIGN_EXCHANGE_G&L` | Fundamentals | Q |  | FS r54 | mn, selected ccy | 0/8 |
| 76 | Fees and Commissions | `FEES_AND_COMMISSIONS` | Fundamentals | Q |  | FS r86 | mn, selected ccy | 0/8 |
| 77 | Other Income Expense | `OTHER_INCOME_EXP` | Fundamentals | Q |  | FS r50 | mn, selected ccy | 0/8 |
| 78 | Loss & Loss Adjustment Expenses | `LOSS_AND_LOSS_ADJUSTMENT_EXPENSES` | Fundamentals | Q |  | FS r113 | mn, selected ccy | 0/8 |
| 79 | Policyholder Interest | `POLICYHOLDER_INT` | Fundamentals | Q |  | FS r114 | mn, selected ccy | 0/8 |
| 80 | Policyholder Dividends | `POLICYHOLDER_DIVIDENDS` | Fundamentals | Q |  | FS r116 | mn, selected ccy | 0/8 |
| 81 | Policy Acquisition Expenses | NOT_ESTABLISHED | Fundamentals | Q |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 82 | Underwriting Expenses | `UNDERWRITING_EXP` | Fundamentals | Q |  | FS r115 | mn, selected ccy | 0/8 |
| 83 | Fees and Commission Expense | `FEES_AND_COMMISSION_EXP` | Fundamentals | Q |  | FS r100 | mn, selected ccy | 0/8 |
| 84 | Change in Insurance Liabilities Net of Reinsurance | `CHANGE_IN_INSURANCE_LIABILITIES_NET_REINSURANCE` | Fundamentals | Q |  | FS r311 | mn, selected ccy | 0/8 |
| 85 | Change in Investment Contract | `CHANGE_IN_INVESTMENT_CONTRACT` | Fundamentals | Q |  | FS r312 | mn, selected ccy | 0/8 |
| 86 | Gross Premiums Written | `GROSS_WRITTEN_PREMIUM` | Fundamentals | Q |  | FS r108 | mn, selected ccy | 0/8 |
| 87 | Ceded Premiums | `CEDED_PREMIUM` | Fundamentals | Q |  | FS r109 | mn, selected ccy | 0/8 |
| 88 | Adjusted Funds From Operations (FFO) | `AFFO` | Income Statement | Q | Y | FS r251 | mn, selected ccy | 0/8 |
| 89 | Adjusted Funds From Operations Per Share | `AFFOPS` | Income Statement | Q | Y | FS r252 | ccy/share | 0/8 |
| 90 | Interest Income from Loans and Leases | `INT_INC_LOANS_LEASE` | Fundamentals | Q |  | FS r82 | mn, selected ccy | 0/8 |
| 91 | Interest Income from Securities | `INT_INC_SECURITIES` | Fundamentals | Q |  | FS r83 | mn, selected ccy | 0/8 |
| 92 | Interest Income from Deposits | `INT_INC_DEPOSITS` | Fundamentals | Q |  | FS r84 | mn, selected ccy | 0/8 |
| 93 | Other Interest Income | `OTHER_INT_INC` | Fundamentals | Q |  | FS r85 | mn, selected ccy | 0/8 |
| 94 | Interest Expense for Deposit | `INT_EXP_FOR_DEPOSIT` | Fundamentals | Q |  | FS r96 | mn, selected ccy | 0/8 |
| 95 | Interest Expense for LTD and Capital Securities | `INT_EXP_LT_DEBT` | Fundamentals | Q |  | FS r97 | mn, selected ccy | 0/8 |
| 96 | Other Interest Expense | `OTHER_INT_EXP` | Fundamentals | Q |  | FS r98 | mn, selected ccy | 0/8 |
| 97 | Net Interest Income | `NET_INT_INC` | Income Statement | Q | Y | FS r101 | mn, selected ccy | 0/8 |
| 98 | Dividend Income | `INC_DIV` | Fundamentals | Q |  | FS r12 | mn, selected ccy | 0/8 |
| 99 | Net Trading Income | `NET_TRADING_INCOME` | Fundamentals | Q |  | FS r87 | mn, selected ccy | 0/8 |
| 100 | Investment Banking Profit | `IB_PROFIT` | Income Statement | Q | Y | FS r91 | mn, selected ccy | 0/8 |
| 101 | Trading Gain/Loss | `TRADING_G&L` | Fundamentals | Q |  | FS r88 | mn, selected ccy | 0/8 |
| 102 | Gain/Loss on Investments | `G&L_ON_INVESTMENTS` | Fundamentals | Q |  | FS r89 | mn, selected ccy | 0/8 |
| 103 | Gain/Loss on Derivatives | `G&L_ON_DERIVATIVES` | Fundamentals | Q |  | FS r90 | mn, selected ccy | 0/8 |
| 104 | Other Non-Interest Revenue | `OTHER_NON_INT_REV` | Fundamentals | Q |  | FS r14 | mn, selected ccy | 0/8 |
| 105 | Non-Interest Revenue | `NON_INT_REV` | Income Statement | Q | Y | FS r13 | mn, selected ccy | 0/8 |
| 106 | Provision for Credit Losses | `CREDIT_LOSSES_PROV` | Fundamentals | Q |  | FS r99 | mn, selected ccy | 0/8 |
| 107 | Other Non-Interest Expense | `OTHER_NONINT_EXP` | Fundamentals | Q |  | FS r36 | mn, selected ccy | 0/8 |
| 108 | Total Non-Interest Expense | `TOTAL_NON_INT_EXP` | Income Statement | Q | Y | FS r37 | mn, selected ccy | 0/8 |
| 109 | Income from Associates and Other Participating Interests | `INCOME_FROM_ASSOCIATES` | Fundamentals | Q |  | FS r94 | mn, selected ccy | 0/8 |
| 110 | Special Income Charges | `SPECIAL_INCOME_CHARGES` | Fundamentals | Q |  | FS r53 | mn, selected ccy | 0/8 |
| 111 | Other Revenue | `OTHER_REVENUE` | Fundamentals | Q |  | FS r11 | mn, selected ccy | 0/8 |
| 112 | Compensation Expense | `COMPENSATION_EXP` | Income Statement | Q | Y | FS r25 | mn, selected ccy | 0/8 |
| 113 | Occupancy and Equipment Expense | `OCCUPANCY_EQUIPMENT_EXP` | Income Statement | Q | Y | FS r26 | mn, selected ccy | 0/8 |
| 114 | Professional Expenses | `PROFESSIONAL_EXP` | Fundamentals | Q |  | FS r27 | mn, selected ccy | 0/8 |
| 115 | Other SG&A Expenses | `OTHER_SG&A_EXP` | Fundamentals | Q |  | FS r28 | mn, selected ccy | 0/8 |
| 116 | Amortization of Securities | `AMORTIZATION_SECURITIES` | Fundamentals | Q |  | FS r105 | mn, selected ccy | 0/8 |
| 117 | Total Assets | `TOT_ASSET` | Balance Sheet | Q | Y | FS r143 | mn, selected ccy | 8/8 |
| 118 | Cash and Cash Equivalents and Short Term Investments | `CASH_AND_ST_INVT` | Balance Sheet | Q | Y | FS r123 | mn, selected ccy | 8/8 |
| 119 | Receivables, Net | `REC_NET` | Balance Sheet | Q | Y | FS r125 | mn, selected ccy | 8/8 |
| 120 | Total Inventory, Net | `INV_NET` | Balance Sheet | Q | Y | FS r128 | mn, selected ccy | 8/8 |
| 121 | Total Current Assets | `CURR_ASSET` | Balance Sheet | Q | Y | FS r131 | mn, selected ccy | 8/8 |
| 122 | PP&E, Net | `PPE_NET` | Balance Sheet | Q | Y | FS r132 | mn, selected ccy | 8/8 |
| 123 | Intangible Assets (Incl. Goodwill) | `INTANGIBLE_INCL_GW` | Balance Sheet | Q | Y | FS r135 | mn, selected ccy | 8/8 |
| 124 | Total Non-Current Assets | `NON_CURR_ASSET` | Balance Sheet | Q | Y | FS r142 | mn, selected ccy | 8/8 |
| 125 | Accounts Payable and Current Accrued Expenses | `PAYABLE_AND_CURR_AE` | Balance Sheet | Q | Y | FS r146 | mn, selected ccy | 8/8 |
| 126 | Total Debt and Lease Obligation | `TOT_DEBT_AND_LEASE` | Balance Sheet | Q | Y | FS r179 | mn, selected ccy | 8/8 |
| 127 | Net Debt | `NET_DEBT` | Balance Sheet | Q | Y | FS r181 | mn, selected ccy | 8/8 |
| 128 | Current Debt and Lease Obligation | `CURR_DEBT_AND_LEASE` | Balance Sheet | Q | Y | FS r154 | mn, selected ccy | 8/8 |
| 129 | Total Current Liabilities | `CURR_LIAB` | Balance Sheet | Q | Y | FS r164 | mn, selected ccy | 8/8 |
| 130 | Long Term Debt and Lease Obligation | `NON_CURR_DEBT_AND_LEASE` | Balance Sheet | Q | Y | FS r167 | mn, selected ccy | 8/8 |
| 131 | Total Non-Current Liabilities | `NON_CURR_LIAB` | Balance Sheet | Q | Y | FS r176 | mn, selected ccy | 8/8 |
| 132 | Total Liabilities | `TOT_LIAB` | Balance Sheet | Q | Y | FS r185 | mn, selected ccy | 8/8 |
| 133 | Total Stockholders Equity | `TOT_SE` | Balance Sheet | Q | Y | FS r199 | mn, selected ccy | 8/8 |
| 134 | Total Stockholders Equity including Minority Interest | `TOT_SE_INCL_NCI` | Balance Sheet | Q | Y | FS r200 | mn, selected ccy | 8/8 |
| 135 | Total Liabilities and Stockholders Equity | `TOT_LIAB_AND_SE` | Balance Sheet | Q | Y | FS r201 | mn, selected ccy | 8/8 |
| 136 | Other Current Assets | `CURR_OTH_ASSET` | Fundamentals | Q |  | FS r130 | mn, selected ccy | 6/8 |
| 137 | Goodwill | `GW` | Fundamentals | Q |  | FS r133 | mn, selected ccy | 8/8 |
| 138 | Intangible Assets (Excl. Goodwill) | `INTANGIBLE_EXCL_GW` | Fundamentals | Q |  | FS r134 | mn, selected ccy | 8/8 |
| 139 | Other Non-Current Assets | `NON_CURR_OTH_ASSET` | Fundamentals | Q |  | FS r140 | mn, selected ccy | 6/8 |
| 140 | Payables | `PAYABLES` | Balance Sheet | Q | Y | FS r148 | mn, selected ccy | 8/8 |
| 141 | Current Accrued Expenses | `CURR_AE` | Fundamentals | Q |  | FS r150 | mn, selected ccy | 0/8 |
| 142 | Current Debt | `CURR_DEBT` | Fundamentals | Q |  | FS r152 | mn, selected ccy | 8/8 |
| 143 | Current Lease Obligation | `CURR_LEASE_LIAB` | Fundamentals | Q |  | FS r153 | mn, selected ccy | 4/8 |
| 144 | Current Deferred Taxes Liabilities | `CURR_DEF_TAX_LIAB` | Fundamentals | Q |  | FS r157 | mn, selected ccy | 0/8 |
| 145 | Current Deferred Revenue | `CURR_DEF_REV` | Fundamentals | Q |  | FS r155 | mn, selected ccy | 0/8 |
| 146 | Current Deferred Liabilities | `CURR_DEF_LIAB` | Fundamentals | Q |  | FS r156 | mn, selected ccy | 5/8 |
| 147 | Current Provisions | `CURR_PROVISIONS` | Fundamentals | Q |  | FS r160 | mn, selected ccy | 0/8 |
| 148 | Other Current Liabilities | `CURR_OTH_LIAB` | Fundamentals | Q |  | FS r163 | mn, selected ccy | 6/8 |
| 149 | Long Term Debt | `NON_CURR_DEBT` | Fundamentals | Q |  | FS r165 | mn, selected ccy | 8/8 |
| 150 | Long Term Lease Obligation | `NON_CURR_LEASE_LIAB` | Fundamentals | Q |  | FS r166 | mn, selected ccy | 8/8 |
| 151 | Long Term Provisions | `NON_CURR_PROVISIONS` | Fundamentals | Q |  | FS r168 | mn, selected ccy | 0/8 |
| 152 | Non-Current Deferred Taxes Liabilities | `NON_CURR_DEF_TAX_LIAB` | Fundamentals | Q |  | FS r171 | mn, selected ccy | 5/8 |
| 153 | Non-Current Deferred Revenue | `NON_CURR_DEF_REV` | Fundamentals | Q |  | FS r169 | mn, selected ccy | 0/8 |
| 154 | Non-Current Deferred Liabilities | `NON_CURR_DEF_LIAB` | Fundamentals | Q |  | FS r170 | mn, selected ccy | 5/8 |
| 155 | Non-Current Pension and Other Post Retirement Benefit Plans | `NON_CURR_PENSION_AND_PRB` | Fundamentals | Q |  | FS r173 | mn, selected ccy | 0/8 |
| 156 | Non-Current Accrued Expenses | `NON_CURR_AE` | Fundamentals | Q |  | FS r174 | mn, selected ccy | 0/8 |
| 157 | Other Non-Current Liabilities | `NON_CURR_OTH_LIAB` | Fundamentals | Q |  | FS r175 | mn, selected ccy | 6/8 |
| 158 | Share Capital | `CAPITAL_STOCK` | Fundamentals | Q |  | FS r187 | mn, selected ccy | 6/8 |
| 159 | Additional Paid-In Capital | `APIC` | Fundamentals | Q |  | FS r191 | mn, selected ccy | 6/8 |
| 160 | Share and Additional Paid-In Capital | `CAPITAL_STOCK_AND_APIC` | Balance Sheet | Q | Y | FS r192 | mn, selected ccy | 0/8 |
| 161 | Retained Earnings | `RETAINED_EARNINGS` | Balance Sheet | Q | Y | FS r193 | mn, selected ccy | 6/8 |
| 162 | Treasury Stock | `TREASURY_STOCK` | Balance Sheet | Q | Y | FS r194 | mn, selected ccy | 1/8 |
| 163 | Other Comprehensive Income | `OTH_COMP_INC` | Fundamentals | Q |  | FS r195 | mn, selected ccy | 6/8 |
| 164 | Other Equity Interest | `OTH_EI` | Fundamentals | Q |  | FS r196 | mn, selected ccy | 0/8 |
| 165 | Minority Interest | `NCI_BS` | Balance Sheet | Q | Y | FS r197 | mn, selected ccy | 0/8 |
| 166 | Net Working Capital | `NET_WC` | Fundamentals | Q |  | FS r204 | mn, selected ccy | 8/8 |
| 167 | Cash and Cash Equivalents | `CASH_AND_EQUIV` | Fundamentals | Q |  | FS r121 | mn, selected ccy | 8/8 |
| 168 | Short Term Investments | `ST_INVT` | Fundamentals | Q |  | FS r122 | mn, selected ccy | 8/8 |
| 169 | Other Payable | `OTH_PAYABLE` | Fundamentals | Q |  | FS r149 | mn, selected ccy | 0/8 |
| 170 | Pension and Other Post Retirement Benefit Plans | `CURR_PENSION_LIAB` | Fundamentals | Q |  | FS r161 | mn, selected ccy | 0/8 |
| 171 | Accrued and Deferred Income, Current (dup) | `CURR_ACCRD_AND_DEF_INC` | Fundamentals | Q |  | FS r159 | mn, selected ccy | 0/8 |
| 172 | Accrued and Deferred Income, Non-Current | `NON_CURR_ACCRD_AND_DEF_INC` | Fundamentals | Q |  | FS r172 | mn, selected ccy | 0/8 |
| 173 | Other Debt/(Cash)Items | `OTH_DEBT_AND_CASH_ITEMS` | Fundamentals | Q |  | FS r180 | mn, selected ccy | 0/8 |
| 174 | Tangible Book Value per Share | `TBVPS` | Balance Sheet | Q | Y | FS r208 | ccy/share | 0/8 |
| 175 | Book Value per Share | `BVPS` | Balance Sheet | Q | Y | FS r206 | ccy/share | 0/8 |
| 176 | Minority Interest and Preferred Stock | `NCI_AND_PREF_STOCK` | Fundamentals | Q |  | FS r198 | mn, selected ccy | 0/8 |
| 177 | Accounts Receivable | `ACCT_REC` | Fundamentals | Q |  | FS r126 | mn, selected ccy | 8/8 |
| 178 | Other Receivables | `OTH_REC` | Fundamentals | Q |  | FS r127 | mn, selected ccy | 5/8 |
| 179 | Accounts Payable | `ACCT_PAYABLE` | Fundamentals | Q |  | FS r147 | mn, selected ccy | 8/8 |
| 180 | Common Stock | `COMMON_STOCK` | Fundamentals | Q |  | FS r188 | mn, selected ccy | 6/8 |
| 181 | Preferred Stock | `PREF_STOCK` | Fundamentals | Q |  | FS r189 | mn, selected ccy | 6/8 |
| 182 | Other Share Capital | `OTH_CAPITAL_STOCK` | Fundamentals | Q |  | FS r190 | mn, selected ccy | 0/8 |
| 183 | Net Loan | `NET_LOAN` | Balance Sheet | Q | Y | FS r222 | mn, selected ccy | 0/8 |
| 184 | Long Term Equity Investment | `LT_EQUITY_INVESTMENTS` | Fundamentals | Q |  | FS r137 | mn, selected ccy | 0/8 |
| 185 | Other Invested Assets | `OTHER_INVESTED_ASSETS` | Fundamentals | Q |  | FS r138 | mn, selected ccy | 0/8 |
| 186 | Total Investments | `TOTAL_INVESTMENTS` | Fundamentals | Q |  | FS r136 | mn, selected ccy | 8/8 |
| 187 | Deferred Policy Acquisition Costs | `DEFERRED_POLICY_ACQUISITION_COSTS` | Fundamentals | Q |  | FS r232 | mn, selected ccy | 0/8 |
| 188 | Other Assets | `OTHER_ASSETS` | Fundamentals | Q |  | FS r141 | mn, selected ccy | 0/8 |
| 189 | Total Policyholder Liabilities | `TOTAL_POLICYHOLDER_LIABILITIES` | Fundamentals | Q |  | FS r235 | mn, selected ccy | 0/8 |
| 190 | Unpaid Loss and Loss Reserve | `UNPAID_LOSS_RESERVE` | Fundamentals | Q |  | FS r236 | mn, selected ccy | 0/8 |
| 191 | Unearned Premiums | `UNEARNED_PREMIUMS` | Fundamentals | Q |  | FS r237 | mn, selected ccy | 0/8 |
| 192 | Future Policy Benefits | `FUTURE_POLICY_BENEFITS` | Fundamentals | Q |  | FS r238 | mn, selected ccy | 0/8 |
| 193 | Policyholder Funds | `POLICYHOLDER_FUNDS` | Fundamentals | Q |  | FS r239 | mn, selected ccy | 0/8 |
| 194 | Total Deposits | `TOTAL_DEPOSITS` | Balance Sheet | Q | Y | FS r225 | mn, selected ccy | 0/8 |
| 195 | Other Liabilities | `OTH_L` | Fundamentals | Q |  | FS r184 | mn, selected ccy | 0/8 |
| 196 | Investment in Financial Assets | `INVESTMENTIN_FINANCIAL_ASSETS` | Fundamentals | Q |  | FS r223 | mn, selected ccy | 0/8 |
| 197 | Reinsurance Assets | `REINSURANCE_ASSETS` | Fundamentals | Q |  | FS r233 | mn, selected ccy | 0/8 |
| 198 | Insurance Contract Liabilities | `INSURANCE_CONTRACT_LIABILITIES` | Fundamentals | Q |  | FS r240 | mn, selected ccy | 0/8 |
| 199 | Investment Contract Liabilities | `INVESTMENT_CONTRACT_LIABILITIES` | Fundamentals | Q |  | FS r241 | mn, selected ccy | 0/8 |
| 200 | Reinsurance Liabilities | `REINSURANCE_BALANCES_PAYABLE` | Fundamentals | Q |  | FS r242 | mn, selected ccy | 0/8 |
| 201 | Tangible Book Value | `TANGIBLE_BOOK_VALUE` | Balance Sheet | Q | Y | FS r207 | mn, selected ccy | 0/8 |
| 202 | Book Value | `BOOK_VALUE` | Balance Sheet | Q | Y | FS r205 | mn, selected ccy | 0/8 |
| 203 | Total Share Count (EoP) | `ORDINARY_SHARES_EOP` | Balance Sheet | Q | Y | FS r211 | mn, selected ccy | 0/8 |
| 204 | Restricted Cash and Investments | `RESTRICTED_CASH_INVESTMENTS` | Fundamentals | Q |  | FS r124 | mn, selected ccy | 0/8 |
| 205 | Federal Funds Sold | `FEDERAL_FUNDS_SOLD` | Fundamentals | Q |  | FS r215 | mn, selected ccy | 0/8 |
| 206 | Total Lease Obligation | `TOT_LEASE_OBL` | Fundamentals | Q |  | FS r178 | mn, selected ccy | 0/8 |
| 207 | Cash and Cash Equivalents and Federal Funds Sold | `CASH_CASH_EQUIVALENTS_FEDERAL_FUNDS` | Fundamentals | Q |  | FS r216 | mn, selected ccy | 0/8 |
| 208 | Securities and Investments | `SECURITIES_AND_INVESTMENTS` | Fundamentals | Q |  | FS r217 | mn, selected ccy | 0/8 |
| 209 | Security Borrowed | `SECURITY_BORROWED` | Fundamentals | Q |  | FS r218 | mn, selected ccy | 0/8 |
| 210 | Gross Loan | `GROSS_LOAN` | Balance Sheet | Q | Y | FS r219 | mn, selected ccy | 0/8 |
| 211 | Allowance for Loans and Lease Losses | `ALLOWANCE_FOR_LOANS_LEASE_LOSSES` | Balance Sheet | Q | Y | FS r220 | mn, selected ccy | 0/8 |
| 212 | Unearned Income | `UNEARNED_INCOME` | Fundamentals | Q |  | FS r221 | mn, selected ccy | 0/8 |
| 213 | Interest Bearing Deposits Liabilities | `INT_BEARING_DEPOSITS_LIABILITIES` | Balance Sheet | Q | Y | FS r226 | mn, selected ccy | 0/8 |
| 214 | Non Interest Bearing Deposits | `NON_INT_BEARING_DEPOSITS` | Balance Sheet | Q | Y | FS r227 | mn, selected ccy | 0/8 |
| 215 | Securities Loaned | `SECURITIES_LOANED` | Fundamentals | Q |  | FS r228 | mn, selected ccy | 0/8 |
| 216 | Trading Liabilities | `TRADING_LIABILITIES` | Fundamentals | Q |  | FS r162 | mn, selected ccy | 0/8 |
| 217 | Deferred Tax Assets | `DEFERRED_TAX_ASSETS` | Balance Sheet | Q | Y | FS r139 | mn, selected ccy | 0/8 |
| 218 | Current Tax Assets | `TAXES_ASSETS_CURRENT` | Fundamentals | Q |  | FS r129 | mn, selected ccy | 0/8 |
| 219 | Accrued Expenses | `ACCRUED_EXP` | Balance Sheet | Q | Y | FS r151 | mn, selected ccy | 0/8 |
| 220 | Deferred Income | `DEFERRED_INCOME` | Fundamentals | Q |  | FS r158 | mn, selected ccy | 0/8 |
| 221 | Accrued and Deferred Income, Current (dup) | `CURR_ACCRD_AND_DEF_INC` | Fundamentals | Q |  | FS r159 | mn, selected ccy | 0/8 |
| 222 | Total Debt  | `DEBT_TOTAL` | Fundamentals | Q |  | FS r177 | mn, selected ccy | 8/8 |
| 223 | Provisions | `PROVISIONS_TOTAL` | Fundamentals | Q |  | FS r182 | mn, selected ccy | 0/8 |
| 224 | Deferred Tax Liabilities | `DEFERRED_TAX_LIABILITIES` | Balance Sheet | Q | Y | FS r183 | mn, selected ccy | 0/8 |
| 225 | Net Interest Margin, % (dup) | `NET_INT_MARGIN` | Margins | Q | Y | RA r85 | percent | 0/8 |
| 226 | Common Equity Tier 1 Ratio, % (dup) | `TIER1_COMM_EQUITY_RATIO` | Margins | Q | Y | RA r82 | percent | 0/8 |
| 227 | Tier 1 Capital Ratio, % (dup) | `TIER1_CAPITAL_RATIO` | Margins | Q | Y | RA r83 | percent | 0/8 |
| 228 | Tier 2 Capital Ratio, % (dup) | `TIER2_CAPITAL_RATIO` | Margins | Q | Y | RA r84 | percent | 0/8 |
| 229 | Net Income (Loss) From Continuing Operations (CF) | `NI_CONTINOP_CF` | Cash Flow Statement | Q | Y | FS r247 | mn, selected ccy | 0/8 |
| 230 | Change in Working Capital | `CHG_IN_WC` | Fundamentals | Q |  | FS r248 | mn, selected ccy | 8/8 |
| 231 | Operating Cash Flow | `OCF` | Cash Flow Statement | Q | Y | FS r245 | mn, selected ccy | 8/8 |
| 232 | Capex | `CAPEX` | Cash Flow Statement | Q | Y | FS r278 | mn, selected ccy | 8/8 |
| 233 | Investing Cash Flow | `ICF` | Cash Flow Statement | Q | Y | FS r277 | mn, selected ccy | 8/8 |
| 234 | Increase/(Decrease) in Debt, Net | `CHG_IN_DEBT_NET` | Cash Flow Statement | Q | Y | FS r293 | mn, selected ccy | 0/8 |
| 235 | Payment of Dividends | `DIV_PYMT` | Fundamentals | Q |  | FS r294 | mn, selected ccy | 0/8 |
| 236 | Financing Cash Flow | `FFCF` | Cash Flow Statement | Q | Y | FS r292 | mn, selected ccy | 8/8 |
| 237 | Cash and Cash Equivalents - Beginning Balance | `CASH_BOP` | Cash Flow Statement | Q | Y | FS r307 | mn, selected ccy | 8/8 |
| 238 | Cash and Cash Equivalents - Ending Balance | `CASH_EOP` | Cash Flow Statement | Q | Y | FS r308 | mn, selected ccy | 8/8 |
| 239 | Depreciation and Amortization | `DA_CF` | Cash Flow Statement | Q | Y | FS r253 | mn, selected ccy | 8/8 |
| 240 | Stock Based Compensation | `SBC_CF` | Cash Flow Statement | Q | Y | FS r254 | mn, selected ccy | 8/8 |
| 241 | Receipts from Customers | `CASH_RECEIPTS_CUSTOMER` | Fundamentals | Q |  | FS r263 | mn, selected ccy | 0/8 |
| 242 | Receipts from Government Grants | `CASH_RECEIPTS_GOVT` | Fundamentals | Q |  | FS r264 | mn, selected ccy | 0/8 |
| 243 | Other Cash Receipts | `CASH_RECEIPTS_OTH` | Fundamentals | Q |  | FS r265 | mn, selected ccy | 0/8 |
| 244 | Classes of Cash Receipts (Operating Activities) | `CASH_RECEIPTS` | Fundamentals | Q |  | FS r266 | mn, selected ccy | 0/8 |
| 245 | Payments to Suppliers for Goods and Services | `CASH_PYMT_SUPPLIERS` | Fundamentals | Q |  | FS r267 | mn, selected ccy | 0/8 |
| 246 | Payments on Behalf of Employees | `CASH_PYMT_EE` | Fundamentals | Q |  | FS r268 | mn, selected ccy | 0/8 |
| 247 | Other Cash Payments | `CASH_PYMT_OTH` | Fundamentals | Q |  | FS r269 | mn, selected ccy | 0/8 |
| 248 | Classes of Cash Payments (Operating Activities) | `CASH_PYMT` | Fundamentals | Q |  | FS r270 | mn, selected ccy | 0/8 |
| 249 | Dividends Paid-Direct | `DIV_PAID_DIRECT` | Fundamentals | Q |  | FS r271 | mn, selected ccy | 5/8 |
| 250 | Dividends Received-Direct | `DIV_RECD_DIRECT` | Fundamentals | Q |  | FS r272 | mn, selected ccy | 0/8 |
| 251 | Interest Paid-Direct | `INT_PAID_DIRECT` | Fundamentals | Q |  | FS r273 | mn, selected ccy | 3/8 |
| 252 | Interest Received-Direct | `INT_RECD_DIRECT` | Fundamentals | Q |  | FS r274 | mn, selected ccy | 0/8 |
| 253 | Taxes Refund Paid-Direct | `TAX_REFUND_PAID_DIRECT` | Fundamentals | Q |  | FS r275 | mn, selected ccy | 0/8 |
| 254 | Deferred Tax | `DEF_TAX` | Fundamentals | Q |  | FS r255 | mn, selected ccy | 6/8 |
| 255 | Other Non-Cash Adjustments | `NON_CASH_ADJMT_OTH` | Fundamentals | Q |  | FS r256 | mn, selected ccy | 0/8 |
| 256 | Change in Receivables | `CHG_IN_WC_REC` | Fundamentals | Q |  | FS r257 | mn, selected ccy | 8/8 |
| 257 | Change in Inventories | `CHG_IN_WC_INV` | Fundamentals | Q |  | FS r258 | mn, selected ccy | 8/8 |
| 258 | Change in Prepaid Assets | `CHG_IN_WC_PREPAID_ASSET` | Fundamentals | Q |  | FS r259 | mn, selected ccy | 5/8 |
| 259 | Change in Payable | `CHG_IN_WC_PAYABLES` | Fundamentals | Q |  | FS r260 | mn, selected ccy | 6/8 |
| 260 | Change in Accrued Expense | `CHG_IN_WC_AE` | Fundamentals | Q |  | FS r261 | mn, selected ccy | 5/8 |
| 261 | Other Changes in Working Capital | `CHG_IN_WC_OTH` | Fundamentals | Q |  | FS r262 | mn, selected ccy | 6/8 |
| 262 | Purchase of PP&E | `PPE_PURCH` | Fundamentals | Q |  | FS r279 | mn, selected ccy | 5/8 |
| 263 | Sale of PP&E | `PPE_SALE` | Fundamentals | Q |  | FS r280 | mn, selected ccy | 0/8 |
| 264 | PPE Purchase and Sale, Net | `PPE_PURCH_NET` | Fundamentals | Q |  | FS r281 | mn, selected ccy | 0/8 |
| 265 | Purchase of Intangibles | `INTANGIBLES_PURCH` | Fundamentals | Q |  | FS r282 | mn, selected ccy | 0/8 |
| 266 | Sale of Intangibles | `INTANGIBLES_SALE` | Fundamentals | Q |  | FS r283 | mn, selected ccy | 0/8 |
| 267 | Intangibles Purchase and Sale, Net | `INTANGIBLES_PURCH_NET` | Fundamentals | Q |  | FS r284 | mn, selected ccy | 0/8 |
| 268 | Acquisitons | `BUSINESS_PURCH` | Fundamentals | Q |  | FS r285 | mn, selected ccy | 6/8 |
| 269 | Divestitures | `BUSINESS_SALE` | Fundamentals | Q |  | FS r286 | mn, selected ccy | 0/8 |
| 270 | Acquisitions/Divestitures, Net | `ACQUISITIONS_NET` | Fundamentals | Q |  | FS r287 | mn, selected ccy | 6/8 |
| 271 | Purchase of Investment | `INVT_PURCH` | Fundamentals | Q |  | FS r288 | mn, selected ccy | 6/8 |
| 272 | Sale of Investment | `INVT_SALE` | Fundamentals | Q |  | FS r289 | mn, selected ccy | 6/8 |
| 273 | Investments Purchase and Sale, Net | `INVT_PURCH_NET` | Fundamentals | Q |  | FS r290 | mn, selected ccy | 0/8 |
| 274 | Other Investing Cash Flow | `OTH_ICF` | Fundamentals | Q |  | FS r291 | mn, selected ccy | 4/8 |
| 275 | Common Stock Issuance, Net | `COMMON_STOCK_ISSUED` | Fundamentals | Q |  | FS r295 | mn, selected ccy | 2/8 |
| 276 | Preferred Stock Issuance, Net | `PREF_STOCK_ISSUED` | Fundamentals | Q |  | FS r296 | mn, selected ccy | 0/8 |
| 277 | Proceeds from Stock Option Exercised | `OPTIONS_EXERCISED` | Fundamentals | Q |  | FS r297 | mn, selected ccy | 6/8 |
| 278 | Other Financing Cash Flow | `OTH_FCF` | Fundamentals | Q |  | FS r298 | mn, selected ccy | 6/8 |
| 279 | Changes in Cash | `CASH_CHG` | Fundamentals | Q |  | FS r305 | mn, selected ccy | 6/8 |
| 280 | Effect of Exchange Rate on Cash and Cash Equivalents | `FX_CASH_EFFECT` | Fundamentals | Q |  | FS r309 | mn, selected ccy | 0/8 |
| 281 | Other Cash Adjustments Outside Change in Cash | `OTH_CASH_ADJMT` | Fundamentals | Q |  | FS r310 | mn, selected ccy | 0/8 |
| 282 | Free Cash Flow | `FCF` | Cash Flow Statement | Q | Y | FS r302 | mn, selected ccy | 8/8 |
| 283 | Free Cash Flow per Share | `FCFPS` | Cash Flow Statement | Q | Y | FS r303 | ccy/share | 5/8 |
| 284 | Increase/(decrease) in Cash and Cash Equivalents | `CASH_NET_CHG` | Cash Flow Statement | Q | Y | FS r306 | mn, selected ccy | 0/8 |
| 285 | Interest Credited on Policyholder Deposits | `INT_CREDITED_POLICY_DEPOSITS` | Fundamentals | Q |  | FS r313 | mn, selected ccy | 0/8 |
| 286 | Change in Loss and Loss Adjustment Expense Reserves | `CHG_LOSS_RESERVES` | Fundamentals | Q |  | FS r314 | mn, selected ccy | 0/8 |
| 287 | Change in Unearned Premiums | `CHG_UNEARNED_PREMIUMS` | Fundamentals | Q |  | FS r315 | mn, selected ccy | 0/8 |
| 288 | Change in Deferred Acquisition Costs | `CHG_DEF_ACQ_COSTS` | Fundamentals | Q |  | FS r316 | mn, selected ccy | 0/8 |
| 289 | Proceeds from Loans | `PROCEEDS_FROM_LOANS` | Fundamentals | Q |  | FS r299 | mn, selected ccy | 0/8 |
| 290 | Payment for Loans | `PAYMENT_FOR_LOANS` | Fundamentals | Q |  | FS r300 | mn, selected ccy | 0/8 |
| 291 | Loan Proceeds and Payment, Net | `NET_PROCEEDS_PAYMENT_FOR_LOAN` | Fundamentals | Q |  | FS r301 | mn, selected ccy | 0/8 |
| 292 | Increase/(Decrease) in Deposit | `INCREASE_DECREASE_IN_DEPOSIT` | Fundamentals | Q |  | FS r317 | mn, selected ccy | 0/8 |
| 293 | Cash Received from Insurance Activities | `CASH_RECEIVED_FROM_INSURANCE` | Fundamentals | Q |  | FS r318 | mn, selected ccy | 0/8 |
| 294 | Cash Receipts from Tax Refunds | `CASH_RECEIPTS_TAX_REFUNDS` | Fundamentals | Q |  | FS r319 | mn, selected ccy | 0/8 |
| 295 | Cash Paid for Insurance Activities | `CASH_PAID_FOR_INSURANCE_ACTIVITIES` | Fundamentals | Q |  | FS r320 | mn, selected ccy | 0/8 |
| 296 | All Taxes Paid | `ALL_TAXES_PAID` | Fundamentals | Q |  | FS r276 | mn, selected ccy | 6/8 |
| 297 | Change in Insurance Contract Assets | `CHANGE_IN_INSURANCE_CONTRACT_ASSETS` | Fundamentals | Q |  | FS r321 | mn, selected ccy | 0/8 |
| 298 | Change in Reinsurance Receivables | `CHANGE_IN_REINSURANCE_RECEIVABLES` | Fundamentals | Q |  | FS r322 | mn, selected ccy | 0/8 |
| 299 | Operating Gains Losses | `OPERATING_G&L` | Fundamentals | Q |  | FS r334 | mn, selected ccy | 0/8 |
| 300 | Provision for Loan Lease and Other Losses | `PROVISION_FOR_LOAN_LEASE` | Fundamentals | Q |  | FS r335 | mn, selected ccy | 0/8 |
| 301 | Provision and Write-Off of Assets | `PROVISION_AND_WRITE_OFF_OF_ASSETS` | Fundamentals | Q |  | FS r336 | mn, selected ccy | 0/8 |
| 302 | Change in Loans | `CHANGE_IN_LOANS` | Fundamentals | Q |  | FS r323 | mn, selected ccy | 0/8 |
| 303 | Change in Financial Assets | `CHANGE_IN_FINANCIAL_ASSETS` | Fundamentals | Q |  | FS r324 | mn, selected ccy | 0/8 |
| 304 | Change in Deposits by Banks and Customers | `CHANGE_IN_DEPOSITS_BANKS_CUSTOMERS` | Fundamentals | Q |  | FS r325 | mn, selected ccy | 0/8 |
| 305 | Change in Financial Liabilities | `CHANGE_IN_FINANCIAL_LIABILITIES` | Fundamentals | Q |  | FS r326 | mn, selected ccy | 0/8 |
| 306 | Cash Receipts from Deposits by Banks and Customers | `CASH_RECEIPTS_FROM_DEPOSITS` | Fundamentals | Q |  | FS r327 | mn, selected ccy | 0/8 |
| 307 | Cash Receipts from Loans | `CASH_RECEIPTS_FROM_LOANS` | Fundamentals | Q |  | FS r328 | mn, selected ccy | 0/8 |
| 308 | Cash Receipts from Securities Related Activities | `CASH_RECEIPTS_FROM_SECURITIES` | Fundamentals | Q |  | FS r329 | mn, selected ccy | 0/8 |
| 309 | Cash Receipts from Fees and Commissions | `CASH_RECEIPTS_FROM_FEES_COMM` | Fundamentals | Q |  | FS r330 | mn, selected ccy | 0/8 |
| 310 | Cash Payments for Deposits by Banks and Customers | `CASH_PAYMENTS_FOR_DEPOSITS` | Fundamentals | Q |  | FS r331 | mn, selected ccy | 0/8 |
| 311 | Cash Payments for Loans | `CASH_PAYMENTS_FOR_LOANS` | Fundamentals | Q |  | FS r332 | mn, selected ccy | 0/8 |
| 312 | Interest and Commission Paid | `INT_AND_COMMISSION_PAID` | Fundamentals | Q |  | FS r333 | mn, selected ccy | 0/8 |
| 313 | Unlevered FCF | `UNLEVERED_FCF` | Fundamentals | Q |  | FS r304 | mn, selected ccy | 0/8 |
| 314 | Operating Cash Flow before WC | `CFO_BEFORE_WC` | Fundamentals | Q |  | FS r246 | mn, selected ccy | 8/8 |
| 315 | Return on Equity | `ROE` | Profitability Ratios | Q | Y | RA r90 | dimensionless | 0/8 |
| 316 | Return on Invested Capital | `ROIC` | Profitability Ratios | Q | Y | RA r91 | dimensionless | 0/8 |
| 317 | Return on Assets | `ROA` | Profitability Ratios | Q | Y | RA r92 | dimensionless | 0/8 |
| 318 | Return on Capital Employed | `ROCE` | Profitability Ratios | Q | Y | RA r93 | dimensionless | 0/8 |
| 319 | Net Interest Margin, % (dup) | `NET_INT_MARGIN` | Margins | Q | Y | RA r85 | percent | 0/8 |
| 320 | Gross Margin (%) | `GROSS_MARGIN` | Fundamentals | Q |  | RA r8 | percent | 0/8 |
| 321 | SG&A Margin (%) | `SGA_MARGIN` | Fundamentals | Q |  | RA r10 | percent | 0/8 |
| 322 | R&D Margin (%) | `RD_MARGIN` | Fundamentals | Q |  | RA r12 | percent | 0/8 |
| 323 | D&A Margin (%) | `DA_MARGIN` | Fundamentals | Q |  | RA r14 | percent | 0/8 |
| 324 | SBC Margin (%) | `SBC_MARGIN` | Fundamentals | Q |  | RA r16 | percent | 0/8 |
| 325 | EBIT Margin, % | `EBIT_MARGIN` | Margins | Q | Y | RA r17 | percent | 0/8 |
| 326 | EBITDA Margin, % | `EBITDA_MARGIN` | Margins | Q | Y | RA r19 | percent | 0/8 |
| 327 | Net Income to Common Shareholders Margin, % | `NI_COMMON_MARGIN` | Margins | Q | Y | RA r22 | percent | 0/8 |
| 328 | Effective Tax Rate | `TAX_RATE` | Margins | Q | Y | FS r61, RA r21 | mn, selected ccy | 0/8; 0/8 |
| 329 | CapEx Margin (%) | `CAPEX_MARGIN` | Fundamentals | Q |  | RA r25 | percent | 0/8 |
| 330 | Unlevered FCF Margin (%) | `UFCF_MARGIN` | Fundamentals | Q |  | RA r27 | percent | 0/8 |
| 331 | Levered FCF Margin (%) | `FCF_MARGIN` | Fundamentals | Q |  | RA r26 | percent | 0/8 |
| 332 | FCF/Net Income to Common Shareholders Margin, % | `FCF_NI_MARGIN` | Margins | Q | Y | RA r24 | percent | 0/8 |
| 333 | Loss Ratio, % | `LOSS_RATIO` | Fundamentals | Q |  | RA r96 | percent | 0/8 |
| 334 | Expense Ratio, % | `EXPENSE_RATIO` | Fundamentals | Q |  | RA r97 | percent | 0/8 |
| 335 | Combined Ratio, % | `COMBINED_RATIO` | Fundamentals | Q |  | RA r98 | percent | 0/8 |
| 336 | Efficiency Ratio, % | `EFFICIENCY_RATIO` | Margins | Q | Y | RA r87 | percent | 0/8 |
| 337 | Cost to Income Ratio, % | `COST_TO_INC_RATIO` | Margins | Q | Y | RA r86 | percent | 0/8 |
| 338 | Common Equity Tier 1 Ratio, % (dup) | `TIER1_COMM_EQUITY_RATIO` | Margins | Q | Y | RA r82 | percent | 0/8 |
| 339 | Tier 1 Capital Ratio, % (dup) | `TIER1_CAPITAL_RATIO` | Margins | Q | Y | RA r83 | percent | 0/8 |
| 340 | Tier 2 Capital Ratio, % (dup) | `TIER2_CAPITAL_RATIO` | Margins | Q | Y | RA r84 | percent | 0/8 |
| 341 | Provision for Credit Losses Margin, % | `CREDIT_LOSSES_PROV_MARGIN` | Margins | Q | Y | RA r101 | percent | 0/8 |
| 342 | Compensation Expense Margin, % | `COMPENSATION_EXPENSE_MARGIN` | Fundamentals | Q |  | RA r102 | percent | 0/8 |
| 343 | Occupancy and Equipment Expense Margin, % | `OCCUPANCY_EQUIPMENT_MARGIN` | Fundamentals | Q |  | RA r103 | percent | 0/8 |
| 344 | Professional Expenses Margin, % | `PROFESSIONAL_EXPENSES_MARGIN` | Fundamentals | Q |  | RA r104 | percent | 0/8 |
| 345 | Adj. Gross Margin, % | `GROSS_MARGIN_ADJ` | Adjusted Margins | Q | Y | RA r9 | percent | 0/8 |
| 346 | Adj. EBIT Margin (%) | `EBIT_MARGIN_ADJ` | Fundamentals | Q |  | RA r18 | percent | 0/8 |
| 347 | Adj. EBITDA Margin (%) | `EBITDA_MARGIN_ADJ` | Fundamentals | Q |  | RA r20 | percent | 0/8 |
| 348 | Adj. Net Income to Common Shareholders Margin (%) | `NI_COMMON_MARGIN_ADJ` | Fundamentals | Q |  | RA r23 | percent | 0/8 |
| 349 | Adj. SG&A Margin, % | `SGA_MARGIN_ADJ` | Adjusted Margins | Q | Y | RA r11 | percent | 0/8 |
| 350 | Adj. R&D Margin, % | `RD_MARGIN_ADJ` | Adjusted Margins | Q | Y | RA r13 | percent | 0/8 |
| 351 | Adj. D&A Margin, % | `DA_MARGIN_ADJ` | Adjusted Margins | Q | Y | RA r15 | percent | 0/8 |
| 352 | Current Ratio | `CURRENT_RATIO` | Liquidity Ratios | Q | Y | RA r41 | dimensionless | 0/8 |
| 353 | Quick Ratio | `QUICK_RATIO` | Liquidity Ratios | Q | Y | RA r42 | dimensionless | 0/8 |
| 354 | Cash Ratio | `CASH_RATIO` | Fundamentals | Q |  | RA r43 | dimensionless | 0/8 |
| 355 | Loan to Assets Ratio, % | `LOAN_TO_ASSETS_RATIO` | Liquidity Ratios | Q | Y | RA r108 | percent | 0/8 |
| 356 | Loan to Deposit Ratio, % | `LOAN_TO_DEPOSIT_RATIO` | Liquidity Ratios | Q | Y | RA r109 | percent | 0/8 |
| 357 | Accounts Receivable Turnover | `RECEIVABLE_TURNOVER` | Operating Ratios | Q | Y | RA r30 | dimensionless | 0/8 |
| 358 | Accounts Payable Turnover | `PAYABLE_TURNOVER` | Operating Ratios | Q | Y | RA r34 | dimensionless | 0/8 |
| 359 | Inventory Turnover | `INVENTORY_TURNOVER` | Operating Ratios | Q | Y | RA r32 | dimensionless | 0/8 |
| 360 | Days Sales Outstanding (DSO) | `DSO` | Operating Ratios | Q | Y | RA r31 | dimensionless | 0/8 |
| 361 | Days Inventory Outstanding (DIO) | `DIO` | Operating Ratios | Q | Y | RA r33 | dimensionless | 0/8 |
| 362 | Days Payable Outstanding (DPO) | `DPO` | Operating Ratios | Q | Y | RA r35 | dimensionless | 0/8 |
| 363 | Cash Conversion Cycle (CCC) | `CCC` | Operating Ratios | Q | Y | RA r36 | dimensionless | 0/8 |
| 364 | Reserves to Surplus Ratio, % | NOT_ESTABLISHED | Fundamentals | Q |  | RA r107 | percent | 0/8 |
| 365 | LT Debt/Equity | `LT_DEBT_TO_EQUITY` | Leverage Ratios | Q | Y | RA r61 | dimensionless | 0/8 |
| 366 | LT Debt/Total Capital | `LT_DEBT_TO_CAPITAL` | Leverage Ratios | Q | Y | RA r62 | dimensionless | 0/8 |
| 367 | LT Debt/Total Assets | `LT_DEBT_TO_ASSET` | Leverage Ratios | Q | Y | RA r63 | dimensionless | 0/8 |
| 368 | Total Debt/Shareholders' Equity | `TOT_DEBT_TO_EQUITY` | Leverage Ratios | Q | Y | RA r59 | dimensionless | 0/8 |
| 369 | Total Debt/Total Capital | `TOT_DEBT_TO_CAPITAL` | Leverage Ratios | Q | Y | RA r60 | dimensionless | 0/8 |
| 370 | Total Debt/Total Assets | `TOT_DEBT_TO_ASSET` | Leverage Ratios | Q | Y | RA r64 | dimensionless | 0/8 |
| 371 | Total Liabilities/Total Assets | `TOT_LIAB_TO_ASSET` | Leverage Ratios | Q | Y | RA r66 | dimensionless | 0/8 |
| 372 | Total Assets/Shareholders' Equity | `TOT_ASSET_TO_EQUITY` | Leverage Ratios | Q | Y | RA r65 | dimensionless | 0/8 |
| 373 | EBIT/Interest Expenses | `EBIT_TO_INT_EXP` | Fundamentals | Q |  | RA r46 | dimensionless | 0/8 |
| 374 | EBITDA/Interest Expenses | `EBITDA_TO_INT_EXP` | Fundamentals | Q |  | RA r47 | dimensionless | 0/8 |
| 375 | (EBITDA-CapEx)/Interest Expenses | `EBITDA_LESS_CAPEX_TO_INT_EXP` | Coverage Ratios | Q | Y | RA r48 | dimensionless | 0/8 |
| 376 | Total Debt/EBITDA | `DEBT_TO_EBITDA` | Coverage Ratios | Q | Y | RA r49 | dimensionless | 0/8 |
| 377 | Total Debt/Operating Cash Flow | `TOT_DEBT_TO_OCF` | Coverage Ratios | Q | Y | RA r51 | dimensionless | 0/8 |
| 378 | Total Debt/(EBITDA-CapEx) | `TOT_DEBT_TO_EBITDA_LESS_CAPEX` | Coverage Ratios | Q | Y | RA r52 | dimensionless | 0/8 |
| 379 | Net Debt/EBITDA | `NET_DEBT_TO_EBITDA` | Coverage Ratios | Q | Y | RA r50 | dimensionless | 0/8 |
| 380 | Net Debt/(EBITDA-CapEx) | `NET_DEBT_TO_EBITDA_LESS_CAPEX` | Coverage Ratios | Q | Y | RA r55 | dimensionless | 0/8 |
| 381 | Net Debt/Operating Cash Flow | `NET_DEBT_TO_OCF` | Coverage Ratios | Q | Y | RA r53 | dimensionless | 0/8 |
| 382 | Unlevered FCF/Total Debt | `UFCF_TO_TOT_DEBT` | Coverage Ratios | Q | Y | RA r54 | dimensionless | 0/8 |
| 383 | Capex/PP&E | `CAPEX_TO_PPE` | Capital Intensity Ratios | Q | Y | RA r70 | dimensionless | 0/8 |
| 384 | Capex/D&A | `CAPEX_TO_DA` | Capital Intensity Ratios | Q | Y | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 385 | D&A/PP&E | `DA_TO_PPE` | Capital Intensity Ratios | Q | Y | RA r71 | dimensionless | 0/8 |
| 386 | Net Working Capital/Average Assets | `NWC_TO_AVG_ASSET` | Fundamentals | Q |  | RA r74 | dimensionless | 0/8 |
| 387 | Fixed Asset Turnover | `FIXED_ASSET_TURNOVER` | Fundamentals | Q |  | RA r72 | dimensionless | 0/8 |
| 388 | Total Asset Turnover | `TOTAL_ASSET_TURNOVER` | Capital Intensity Ratios | Q | Y | RA r73 | dimensionless | 0/8 |
| 389 | Dividend Payout Ratio, % | `DIV_PAYOUT_RATIO` | Fundamentals | Q |  | RA r78 | percent | 0/8 |
| 390 | LTM Dividend Payout Ratio (%) | `LTM_DIV_PAYOUT_RATIO` | Fundamentals | LTM |  | RA r79 | percent | 0/8 |
| 391 | P/E | `PE` | Trading Multiples | D/M | Y | RA r112, TM | dimensionless | 8/8; n=254 |
| 392 | Adj. P/E | `PE_ADJ` | Trading Multiples | D/M | Y | RA r113, TM | dimensionless | 8/8; n=375 |
| 393 | P/Sales | `P_TO_SALES` | Trading Multiples | D/M | Y | RA r114, TM | dimensionless | 8/8; n=254 |
| 394 | P/Adj. Sales | `P_TO_SALES_ADJ` | Trading Multiples | D/M | Y | RA r115, TM | dimensionless | 0/8; n=0 |
| 395 | P/BV | `P_TO_BV` | Trading Multiples | D/M | Y | RA r116, TM | dimensionless | 0/8; n=0 |
| 396 | P/TBV | `P_TO_TBV` | Trading Multiples | D/M | Y | RA r117, TM | dimensionless | 0/8; n=0 |
| 397 | P/CashFlow | `P_TO_CF` | Trading Multiples | D/M | Y | RA r118 | dimensionless | 8/8 |
| 398 | P/FCF | `P_TO_FCF` | Trading Multiples | D/M | Y | RA r119, TM | dimensionless | 8/8; n=254 |
| 399 | P/FFO | `P_TO_FFO` | Trading Multiples | D/M | Y | RA r137 | dimensionless | 0/8 |
| 400 | EV/Sales | `EV_TO_SALES` | Trading Multiples | D/M | Y | RA r121, TM | dimensionless | 8/8; n=254 |
| 401 | EV/Adj. Sales | `EV_TO_SALES_ADJ` | Trading Multiples | D/M | Y | RA r122, TM | dimensionless | 0/8; n=0 |
| 402 | EV/Gross Profit | `EV_TO_GP` | Trading Multiples | D/M | Y | RA r123, TM | dimensionless | 6/8; n=254 |
| 403 | EV/Adj. Gross Profit | `EV_TO_GP_ADJ` | Trading Multiples | D/M | Y | RA r124, TM | dimensionless | 8/8; n=375 |
| 404 | EV/EBITDA | `EV_TO_EBITDA` | Trading Multiples | D/M | Y | RA r125, TM | dimensionless | 8/8; n=254 |
| 405 | EV/Adj. EBITDA | `EV_TO_EBITDA_ADJ` | Trading Multiples | D/M | Y | RA r126, TM | dimensionless | 8/8; n=375 |
| 406 | EV/EBIT | `EV_TO_EBIT` | Trading Multiples | D/M | Y | RA r127, TM | dimensionless | 8/8; n=254 |
| 407 | EV/Adj. EBIT | `EV_TO_EBIT_ADJ` | Trading Multiples | D/M | Y | RA r128, TM | dimensionless | 8/8; n=375 |
| 408 | EV/FCF | `EV_TO_FCF` | Trading Multiples | D/M | Y | RA r129, TM | dimensionless | 8/8; n=254 |
| 409 | EV/(EBITDA-CapEx) | `EV_TO_EBITDA_LESS_CAPEX` | Trading Multiples | D/M | Y | RA r130 | dimensionless | 0/8 |
| 410 | Adj. EV/(EBITDA-CapEx) | `EV_TO_EBITDA_ADJ_LESS_CAPEX` | Trading Multiples | Q | Y | RA r131 | dimensionless | 0/8 |
| 411 | FCF Yield (based on Market Cap) | `FCF_YIELD_MCAP` | Trading Multiples | Q | Y | RA r132, TM | percent | 8/8; n=254 |
| 412 | Unlevered FCF Yield, % | `UFCF_YIELD_EV` | Trading Multiples | Q | Y | RA r133 | percent | 0/8 |
| 413 | Dividend Yield (%) | `DIV_YIELD` | Valuation multiples | Q |  | RA r77 | percent | 0/8 |
| 414 | PEG | `PEG` | Trading Multiples | Q | Y | RA r134, TM | dimensionless | 0/8; n=0 |
| 415 | Net Debt/EV | `NET_DEBT_TO_EV` | Trading Multiples | Q | Y | RA r135, TM | dimensionless | 8/8; n=254 |
| 416 | Total Debt/EV | `TOT_DEBT_TO_EV` | Trading Multiples | Q | Y | RA r136, TM | dimensionless | 8/8; n=254 |
| 417 | P/AFFO | `P_TO_AFFO` | Trading Multiples | Q | Y | RA r120, TM | dimensionless | 0/8; n=0 |
| 418 | Market Capitalization | `MCAP` | Market data | D/M |  | RA r138, TM | mn, trading ccy (NVDA: USD mn) | 6/8; n=375 |
| 419 | Enterprise Value | `EV` | Market data | D/M |  | RA r139, TM | mn, trading ccy (NVDA: USD mn) | 6/8; n=375 |
| 420 | Total Shares Outstanding (EoP Basic) | NOT_ESTABLISHED | Market data | Q |  | RA r140 | dimensionless | 0/8 |
| 421 | Shares per Listing | NOT_ESTABLISHED | Market data | Q |  | RA r141 | dimensionless | 0/8 |
| 422 | Enterprise Value per Share | NOT_ESTABLISHED | Market data | D/M |  | RA r142 | ccy/share | 0/8 |
| 423 | Stock Price (End Of Day) | NOT_ESTABLISHED | Market data | D/M |  | RA r143 | dimensionless | 0/8 |
| 424 | Stock Price-Open | `OPEN` | Market data | D/M |  | RA r144 | dimensionless | 6/8 |
| 425 | Stock Price-High | `HIGH` | Market data | D/M |  | RA r145 | dimensionless | 6/8 |
| 426 | Stock Price-Low | `LOW` | Market data | D/M |  | RA r146 | dimensionless | 6/8 |
| 427 | Share Price | `CLOSE` | Market data | D/M |  | FP r17, TM | NOT_ESTABLISHED | empty; n=375 |
| 428 | Last Close Price | `CLOSE_LAST` | Market data | D/M |  | FP r18 | NOT_ESTABLISHED | empty |
| 429 | Last Traded Price | NOT_ESTABLISHED | Market data | D/M |  | RA r147 | dimensionless | 0/8 |
| 430 | Last Transaction Volume | NOT_ESTABLISHED | Market data | D/M |  | RA r148 | dimensionless | 0/8 |
| 431 | Last Trade Date Time | NOT_ESTABLISHED | Market data | D/M |  | RA r149 | date | 0/8 |
| 432 | 52 Week High | `52WK_HIGH` | Market data | W |  | FP r22 | NOT_ESTABLISHED | empty |
| 433 | 52 Week High Date | `52WK_HIGH_DATE` | Market data | W |  | FP r24 | date | empty |
| 434 | 52 Week High Change, % | `52WK_HIGH_PCT_CHG` | Market data | W |  | FP r23 | percent | empty |
| 435 | 52 Week Low | `52WK_LOW` | Market data | W |  | FP r25 | NOT_ESTABLISHED | empty |
| 436 | 52 Week Low Date | `52WK_LOW_DATE` | Market data | W |  | FP r27 | date | empty |
| 437 | 52 Week Low Change, % | `52WK_LOW_PCT_CHG` | Market data | W |  | FP r26 | percent | empty |
| 438 | Daily Volume | `VOLUME` | Market data | D/M |  | FP r19 | NOT_ESTABLISHED | empty |
| 439 | Average Daily Volume | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 440 | Dollar Volume Liquidity | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 441 | 10 Day Dollar Volume Liquidity | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 442 | 20 Day Dollar Volume Liquidity | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 443 | 30 Day Dollar Volume Liquidity | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 444 | 60 Day Dollar Volume Liquidity | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 445 | 90 Day Dollar Volume Liquidity | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 446 | Intraday Cummulative Trade Volume (live) | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 447 | Intraday Stock Price Change (Live), % | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | percent | n/a |
| 448 | Stock Price Percent Change | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 449 | Intraday Price Change (live) | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 450 | Stock Price Change (abs) | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 451 | Total Return | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 452 | Total Return Index | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 453 | Stock Price Return | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 454 | Stock Price Return Index | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 455 | VWAP | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 456 | YTD Price | NOT_ESTABLISHED | Market data | LTM |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 457 | YTD Change | NOT_ESTABLISHED | Market data | LTM |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 458 | YTD,% Change | NOT_ESTABLISHED | Market data | LTM |  | none (W1 list only) | percent | n/a |
| 459 | Previous Day Close | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 460 | Previous Close Date | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | date | n/a |
| 461 | 10 Day Average Daily Volume | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 462 | 20 Day Average Daily Volume | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 463 | 30 Day Average Daily Volume | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 464 | 60 Day Average Daily Volume | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 465 | 90 Day Average Daily Volume | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 466 | MIC | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 467 | Stock Price change (live) | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 468 | Stock Price Change (Live), % | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | percent | n/a |
| 469 | FX Rate | NOT_ESTABLISHED | Market data | D/M |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 470 | Price Target - Mean | `PRICE_TARGET` | Consensus ratings/targets | M |  | FP r39 | NOT_ESTABLISHED | empty |
| 471 | Price Target - Median | `PRICE_TARGET_MEDIAN` | Consensus ratings/targets | M |  | FP r40 | NOT_ESTABLISHED | empty |
| 472 | Price Target - Low | `PRICE_TARGET_LOW` | Consensus ratings/targets | M |  | FP r41 | NOT_ESTABLISHED | empty |
| 473 | Price Target - High | `PRICE_TARGET_HIGH` | Consensus ratings/targets | M |  | FP r42 | NOT_ESTABLISHED | empty |
| 474 | Price Target - Number of Contributors | `PRICE_TARGET_CONTRIBUTORS` | Consensus ratings/targets | M |  | FP r43 | NOT_ESTABLISHED | empty |
| 475 | Price Target - Standard Deviation | `PRICE_TARGET_SD` | Consensus ratings/targets | M |  | FP r44 | NOT_ESTABLISHED | empty |
| 476 | Rating - Number of Strong Buys | `RATING_NUM_STRONG_BUYS` | Consensus ratings/targets | M |  | FP r30 | NOT_ESTABLISHED | empty |
| 477 | Rating - Number of Buys | `RATING_NUM_BUYS` | Consensus ratings/targets | M |  | FP r31 | NOT_ESTABLISHED | empty |
| 478 | Rating - Number of Holds | `RATING_NUM_HOLDS` | Consensus ratings/targets | M |  | FP r32 | NOT_ESTABLISHED | empty |
| 479 | Rating - Number of Sells | `RATING_NUM_SELLS` | Consensus ratings/targets | M |  | FP r33 | NOT_ESTABLISHED | empty |
| 480 | Rating - Number of Strong Sells | `RATING_NUM_STRONG_SELLS` | Consensus ratings/targets | M |  | FP r34 | NOT_ESTABLISHED | empty |
| 481 | Rating - Mean Recommendation | `RATING_MEAN` | Consensus ratings/targets | M |  | FP r35 | NOT_ESTABLISHED | empty |
| 482 | Rating - Label | `RATING_LABEL` | Consensus ratings/targets | M |  | FP r29 | NOT_ESTABLISHED | empty |
| 483 | Rating - No Opinion | `RATING_NO_OPINION` | Consensus ratings/targets | M |  | FP r36 | NOT_ESTABLISHED | empty |
| 484 | Rating - Number of Recommendations | `RATING_NUM_RECOMMENDATIONS` | Consensus ratings/targets | M |  | FP r37 | NOT_ESTABLISHED | v |
| 485 | Company Name | `NAME` | Reference (static) | N/A |  | FP r7 | NOT_ESTABLISHED | v |
| 486 | Sector (GICS L1) | `SECTOR_GICS` | Reference (static) | N/A |  | FP r10 | NOT_ESTABLISHED | v |
| 487 | Industry Group (GICS L2) | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 488 | Industry (GICS L3) | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 489 | Sub-sector (GICS L4) | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 490 | Security Type | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 491 | Country of Incorporation | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 492 | Country of Headquaters | `COUNTRY_HQ` | Reference (static) | N/A |  | FP r8 | NOT_ESTABLISHED | v |
| 493 | Country of Stock Exchange | `COUNTRY_EXCH` | Reference (static) | N/A |  | FP r13 | NOT_ESTABLISHED | v |
| 494 | Quote Name | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 495 | Security Name | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 496 | Issuer Name | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 497 | Stock Exchange | `EXCH` | Reference (static) | N/A |  | FP r14 | NOT_ESTABLISHED | v |
| 498 | Trading Currency | `TRADING_CURR` | Reference (static) | N/A |  | FP r9 | NOT_ESTABLISHED | v |
| 499 | Reporting Currency | `REPORTING_CURR` | Reference (static) | N/A |  | FP r12 | NOT_ESTABLISHED | v |
| 500 | Employee Count | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 501 | Employees (Latest) | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 502 | Earnings Date | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | date | n/a |
| 503 | Financial Period End Date | `FINANCIAL_PERIOD_END_DATE` | Reference (static) | N/A |  | FP r15 | date | v |
| 504 | Financial Period | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 505 | Company Website | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 506 | City | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 507 | State/Region | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 508 | Postcode | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 509 | Full Business Address | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 510 | Company Description | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 511 | IPO Date | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | date | n/a |
| 512 | IPO Offer Price | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 513 | Peers & Competitors | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | NOT_ESTABLISHED | n/a |
| 514 | Exact Period End Date | NOT_ESTABLISHED | Reference (static) | N/A |  | none (W1 list only) | date | n/a |

Code conflict footnote: label `P/AFFO` maps to `P_TO_AFFO` in W1 Available Consensus (row 166) but to code `P_TO_FFO` on W2 Ratios row 120 (provider label/code mismatch; W2 Ratios row 137 `P/FFO` also uses `P_TO_FFO`).

## Section 2 — Consensus-sheet name variants not in Section 1 (16 rows)

These names exist only in W1 `Available Consensus`; most are punctuation/`_2` variants of Section-1 names. They carry codes and consensus availability by definition.

| AC row | name | excel_code | category |
|--------|------|------------|----------|
| 4 | Adj. EBIT Margin, % | `EBIT_MARGIN_ADJ` | Adjusted Margins |
| 6 | Adj. EBITDA Margin, % | `EBITDA_MARGIN_ADJ` | Adjusted Margins |
| 8 | Adj. Net Income to Common Shareholders Margin, % | `NI_COMMON_MARGIN_ADJ` | Adjusted Margins |
| 47 | Net Interest Margin_2, % | `NET_INT_MARGIN_2` | Balance Sheet |
| 48 | Common Equity Tier 1 Ratio_2, % | `TIER1_COMM_EQUITY_RATIO_2` | Balance Sheet |
| 49 | Tier 1 Capital Ratio_2, % | `TIER1_CAPITAL_RATIO_2` | Balance Sheet |
| 50 | Tier 2 Capital Ratio_2, % | `TIER2_CAPITAL_RATIO_2` | Balance Sheet |
| 76 | LTM Dividend Payout Ratio, % | `LTM_DIV_PAYOUT_RATIO` | Dividend Summary |
| 121 | Unlevered FCF Margin, % | `UFCF_MARGIN` | Margins |
| 123 | SG&A Margin, % | `SGA_MARGIN` | Margins |
| 124 | R&D Margin, % | `RD_MARGIN` | Margins |
| 126 | Capex Margin, % | `CAPEX_MARGIN` | Margins |
| 137 | Levered FCF Margin, % | `FCF_MARGIN` | Margins |
| 138 | D&A Margin, % | `DA_MARGIN` | Margins |
| 139 | Gross Margin, % | `GROSS_MARGIN` | Margins |
| 165 | Dividend Yield, % | `DIV_YIELD` | Trading Multiples |

## Section 3 — W2-only labels not in W1 (4 rows)

| Source | name | excel_code | note |
|--------|------|------------|------|
| RA r69 | CapEx/D&A | `CAPEX_TO_DA` | case variant of W1 `Capex/D&A` (row 380) |
| FP r20 | Shares Outstanding (in mm) | `SHARES_OUTSTANDING` | FP variant of `Total Shares Outstanding (EoP Basic)` |
| FP r11 | Sub-Sector (GICS L4) | `SUB_INDUSTRY_GICS` | case variant of W1 `Sub-sector (GICS L4)` |
| TM | P/Cashflow | `P_TO_CF` | case variant of W1 `P/CashFlow` |

## Section 4 — M&A deal fields (W1 col G: 258 fields)

Deal-level dataset (one record per transaction), not per-security time series. No excel codes, frequencies, or tab mappings are given in either workbook — all NOT_ESTABLISHED. Units only where the label states them; role qualifiers `(Target)/(Buyer)/(Seller)/(Parent Of Target)`.

| W1 row | field | units (from label) |
|--------|-------|--------------------|
| 2 | Announcement Date | date |
| 3 | Close Date | date |
| 4 | Deal Status | NOT_ESTABLISHED |
| 5 | Name(Buyer) | NOT_ESTABLISHED |
| 6 | Name(Target) | NOT_ESTABLISHED |
| 7 | Industry(Target) | NOT_ESTABLISHED |
| 8 | Country(Target) | NOT_ESTABLISHED |
| 9 | Adjusted Deal Value (Usd, Mn) | USD mn |
| 10 | Deal Summary | NOT_ESTABLISHED |
| 11 | Deal Attitude | NOT_ESTABLISHED |
| 12 | Cancellation Date | date |
| 13 | Deal Types | NOT_ESTABLISHED |
| 14 | Primary Deal Type | NOT_ESTABLISHED |
| 15 | Expected Close Date | date |
| 16 | Deal Purpose | NOT_ESTABLISHED |
| 17 | Rumour Date | date |
| 18 | Value Of The Base Equity (Usd, Mn) | USD mn |
| 19 | Cash Portion Of Deal Financing (Usd) (Usd, Mn) | USD mn |
| 20 | Cash And Cash Eq. (Pit) (Target) (Usd, Mn) | USD mn |
| 21 | Price / Share (Pps) (Cash Only) | NOT_ESTABLISHED |
| 22 | # Common Shares Acquired (Th) | NOT_ESTABLISHED |
| 23 | # Common Shares Sought (Th) | NOT_ESTABLISHED |
| 24 | # Shares Issued To Target (Th) | NOT_ESTABLISHED |
| 25 | Contingent Payment As Part Of The Deal Financing (Usd) (Usd, Mn) | USD mn |
| 26 | Expected Contingent Payment Payout Date | date |
| 27 | Convertible Debt Portion Of Deal Financing (Usd) (Usd, Mn) | USD mn |
| 28 | Convertible Preferred Shares Portion Of Deal Financing (Usd) (Usd, Mn) | USD mn |
| 29 | Debt Portion Of Deal Financing (Usd) (Usd, Mn) | USD mn |
| 30 | Ev (Pit) (Target) (Usd, Mn) | USD mn |
| 31 | Future Payout As Part Of The Deal Financing (Usd) (Usd, Mn) | USD mn |
| 32 | Interest Bearing Debt (Pit) (Target) (Usd, Mn) | USD mn |
| 33 | Liabilities Assumed As Part Of The Deal Financing (Usd) (Usd, Mn) | USD mn |
| 34 | Deal Financing Type | NOT_ESTABLISHED |
| 35 | Other Means Of Payment As Part Of The Deal Financing (Usd) (Usd, Mn) | USD mn |
| 36 | Share Of The Company'S Equity Pre-Owned (%) | percent |
| 37 | Share Of The Company'S Equity Sought (%) | percent |
| 38 | Preferred Shares Portion Of Deal Financing (Usd) (Usd, Mn) | USD mn |
| 39 | Price / Share (Pps) | NOT_ESTABLISHED |
| 40 | Source Of Funds | NOT_ESTABLISHED |
| 41 | Stock Portion Of Deal Financing (Usd) (Usd, Mn) | USD mn |
| 42 | Transaction Size (Usd, Mn) | USD mn |
| 43 | Warrants And Options Portion Of Deal Financing (Usd) (Usd, Mn) | USD mn |
| 44 | Break-Up Fee To Be Paid By(Target) (Usd, Mn) | USD mn |
| 45 | Break-Up Fee To Be Paid By(Buyer) (Usd, Mn) | USD mn |
| 46 | Break-Up Fee To Be Paid By(Parent Of Target) (Usd, Mn) | USD mn |
| 47 | Break-Up Fee To Be Paid By(Parent Of Buyer) (Usd, Mn) | USD mn |
| 48 | Break-Up Fee To Be Paid By(Buyer - Pe) (Usd, Mn) | USD mn |
| 49 | Break-Up Fee To Be Paid By(Seller - Pe) (Usd, Mn) | USD mn |
| 50 | Additional Commitments(Target) | NOT_ESTABLISHED |
| 51 | Additional Commitments(Buyer) | NOT_ESTABLISHED |
| 52 | Net Tangible Book Value Of Equity (Pit)(Target) (Usd, Mn) | USD mn |
| 53 | Net Tangible Book Value Of Equity (Pit)(Buyer) (Usd, Mn) | USD mn |
| 54 | Net Tangible Book Value Of Equity (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 55 | Net Tangible Book Value Of Equity (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 56 | Total Cash & Eq. (Pit)(Target) (Usd, Mn) | USD mn |
| 57 | Total Cash & Eq. (Pit)(Buyer) (Usd, Mn) | USD mn |
| 58 | Total Cash & Eq. (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 59 | Total Cash & Eq. (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 60 | Net Tangible Book Value Per Share Of Equity (Pit)(Target) | NOT_ESTABLISHED |
| 61 | Net Tangible Book Value Per Share Of Equity (Pit)(Buyer) | NOT_ESTABLISHED |
| 62 | Net Tangible Book Value Per Share Of Equity (Pit)(Parent Of Target) | NOT_ESTABLISHED |
| 63 | Net Tangible Book Value Per Share Of Equity (Pit)(Parent Of Buyer) | NOT_ESTABLISHED |
| 64 | Current Portion Of Cap. Lease. Obligations (Pit)(Target) (Usd, Mn) | USD mn |
| 65 | Current Portion Of Cap. Lease. Obligations (Pit)(Buyer) (Usd, Mn) | USD mn |
| 66 | Current Portion Of Cap. Lease. Obligations (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 67 | Current Portion Of Cap. Lease. Obligations (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 68 | Current Portion Of Lt Debt (Pit)(Target) (Usd, Mn) | USD mn |
| 69 | Current Portion Of Lt Debt (Pit)(Buyer) (Usd, Mn) | USD mn |
| 70 | Current Portion Of Lt Debt (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 71 | Current Portion Of Lt Debt (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 72 | D&A Exp. (Ltm) (Pit)(Target) (Usd, Mn) | USD mn |
| 73 | D&A Exp. (Ltm) (Pit)(Buyer) (Usd, Mn) | USD mn |
| 74 | D&A Exp. (Ltm) (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 75 | D&A Exp. (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 76 | Ebitda (Ltm) (Pit)(Target) (Usd, Mn) | USD mn |
| 77 | Ebitda (Ltm) (Pit)(Buyer) (Usd, Mn) | USD mn |
| 78 | Ebitda (Ltm) (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 79 | Ebitda (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 80 | Ebit (Ltm) (Pit)(Target) (Usd, Mn) | USD mn |
| 81 | Ebit (Ltm) (Pit)(Buyer) (Usd, Mn) | USD mn |
| 82 | Ebit (Ltm) (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 83 | Ebit (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 84 | Eps (Ltm) (Pit)(Target) | NOT_ESTABLISHED |
| 85 | Eps (Ltm) (Pit)(Buyer) | NOT_ESTABLISHED |
| 86 | Eps (Ltm) (Pit)(Parent Of Target) | NOT_ESTABLISHED |
| 87 | Eps (Ltm) (Pit)(Parent Of Buyer) | NOT_ESTABLISHED |
| 88 | Total Diluted Shares Outstanding (Pit)(Target) (Th) | NOT_ESTABLISHED |
| 89 | Total Diluted Shares Outstanding (Pit)(Buyer) (Th) | NOT_ESTABLISHED |
| 90 | Total Diluted Shares Outstanding (Pit)(Parent Of Target) (Th) | NOT_ESTABLISHED |
| 91 | Total Diluted Shares Outstanding (Pit)(Parent Of Buyer) (Th) | NOT_ESTABLISHED |
| 92 | Interest Exp. (Ltm) (Pit)(Target) (Usd, Mn) | USD mn |
| 93 | Interest Exp. (Ltm) (Pit)(Buyer) (Usd, Mn) | USD mn |
| 94 | Interest Exp. (Ltm) (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 95 | Interest Exp. (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 96 | Lt Debt  (Pit)(Target) (Usd, Mn) | USD mn |
| 97 | Lt Debt  (Pit)(Buyer) (Usd, Mn) | USD mn |
| 98 | Lt Debt  (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 99 | Lt Debt  (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 100 | Notes Payables (Pit)(Target) (Usd, Mn) | USD mn |
| 101 | Notes Payables (Pit)(Buyer) (Usd, Mn) | USD mn |
| 102 | Notes Payables (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 103 | Notes Payables (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 104 | Other Short Term Debt (Pit)(Target) (Usd, Mn) | USD mn |
| 105 | Other Short Term Debt (Pit)(Buyer) (Usd, Mn) | USD mn |
| 106 | Other Short Term Debt (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 107 | Other Short Term Debt (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 108 | Profit Before Tax (Ltm) (Pit)(Target) (Usd, Mn) | USD mn |
| 109 | Profit Before Tax (Ltm) (Pit)(Buyer) (Usd, Mn) | USD mn |
| 110 | Profit Before Tax (Ltm) (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 111 | Profit Before Tax (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 112 | Revenue (Ltm) (Pit)(Target) (Usd, Mn) | USD mn |
| 113 | Revenue (Ltm) (Pit)(Buyer) (Usd, Mn) | USD mn |
| 114 | Revenue (Ltm) (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 115 | Revenue (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 116 | Total Shares Outstanding (Pit)(Target) (Th) | NOT_ESTABLISHED |
| 117 | Total Shares Outstanding (Pit)(Buyer) (Th) | NOT_ESTABLISHED |
| 118 | Total Shares Outstanding (Pit)(Parent Of Target) (Th) | NOT_ESTABLISHED |
| 119 | Total Shares Outstanding (Pit)(Parent Of Buyer) (Th) | NOT_ESTABLISHED |
| 120 | Total Assets (Pit)(Target) (Usd, Mn) | USD mn |
| 121 | Total Assets (Pit)(Buyer) (Usd, Mn) | USD mn |
| 122 | Total Assets (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 123 | Total Assets (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 124 | Total Deposits (Pit)(Target) (Usd, Mn) | USD mn |
| 125 | Total Deposits (Pit)(Buyer) (Usd, Mn) | USD mn |
| 126 | Total Deposits (Pit)(Parent Of Target) (Usd, Mn) | USD mn |
| 127 | Total Deposits (Pit)(Parent Of Buyer) (Usd, Mn) | USD mn |
| 128 | City, State, And Post Code(Target) | NOT_ESTABLISHED |
| 129 | City, State, And Post Code(Buyer) | NOT_ESTABLISHED |
| 130 | City, State, And Post Code(Parent Of Target) | NOT_ESTABLISHED |
| 131 | City, State, And Post Code(Parent Of Buyer) | NOT_ESTABLISHED |
| 132 | City, State, And Post Code(Buyer - Pe) | NOT_ESTABLISHED |
| 133 | City, State, And Post Code(Seller - Pe) | NOT_ESTABLISHED |
| 134 | Country(Buyer) | NOT_ESTABLISHED |
| 135 | Country(Parent Of Target) | NOT_ESTABLISHED |
| 136 | Country(Parent Of Buyer) | NOT_ESTABLISHED |
| 137 | Country(Buyer - Pe) | NOT_ESTABLISHED |
| 138 | Country(Seller - Pe) | NOT_ESTABLISHED |
| 139 | Name(Parent Of Target) | NOT_ESTABLISHED |
| 140 | Name(Parent Of Buyer) | NOT_ESTABLISHED |
| 141 | Name(Buyer - Pe) | NOT_ESTABLISHED |
| 142 | Name(Seller - Pe) | NOT_ESTABLISHED |
| 143 | Fax Number (Target) | NOT_ESTABLISHED |
| 144 | Fax Number (Buyer) | NOT_ESTABLISHED |
| 145 | Fax Number (Parent Of Target) | NOT_ESTABLISHED |
| 146 | Fax Number (Parent Of Buyer) | NOT_ESTABLISHED |
| 147 | Fax Number (Buyer - Pe) | NOT_ESTABLISHED |
| 148 | Fax Number (Seller - Pe) | NOT_ESTABLISHED |
| 149 | Latest 10K Date (Pit)(Target) | date |
| 150 | Latest 10K Date (Pit)(Buyer) | date |
| 151 | Latest 10K Date (Pit)(Parent Of Target) | date |
| 152 | Latest 10K Date (Pit)(Parent Of Buyer) | date |
| 153 | Street Address (Line 1) (Target) | NOT_ESTABLISHED |
| 154 | Street Address (Line 1) (Buyer) | NOT_ESTABLISHED |
| 155 | Street Address (Line 1) (Parent Of Target) | NOT_ESTABLISHED |
| 156 | Street Address (Line 1) (Parent Of Buyer) | NOT_ESTABLISHED |
| 157 | Street Address (Line 1) (Buyer - Pe) | NOT_ESTABLISHED |
| 158 | Street Address (Line 1) (Seller - Pe) | NOT_ESTABLISHED |
| 159 | Street Address (Line 2) (Target) | NOT_ESTABLISHED |
| 160 | Street Address (Line 2) (Buyer) | NOT_ESTABLISHED |
| 161 | Street Address (Line 2) (Parent Of Target) | NOT_ESTABLISHED |
| 162 | Street Address (Line 2) (Parent Of Buyer) | NOT_ESTABLISHED |
| 163 | Street Address (Line 2) (Buyer - Pe) | NOT_ESTABLISHED |
| 164 | Street Address (Line 2) (Seller - Pe) | NOT_ESTABLISHED |
| 165 | Street Address (Line 3) (Target) | NOT_ESTABLISHED |
| 166 | Street Address (Line 3) (Buyer) | NOT_ESTABLISHED |
| 167 | Street Address (Line 3) (Parent Of Target) | NOT_ESTABLISHED |
| 168 | Street Address (Line 3) (Parent Of Buyer) | NOT_ESTABLISHED |
| 169 | Street Address (Line 3) (Buyer - Pe) | NOT_ESTABLISHED |
| 170 | Street Address (Line 3) (Seller - Pe) | NOT_ESTABLISHED |
| 171 | Phone Number (Target) | NOT_ESTABLISHED |
| 172 | Phone Number (Buyer) | NOT_ESTABLISHED |
| 173 | Phone Number (Parent Of Target) | NOT_ESTABLISHED |
| 174 | Phone Number (Parent Of Buyer) | NOT_ESTABLISHED |
| 175 | Phone Number (Buyer - Pe) | NOT_ESTABLISHED |
| 176 | Phone Number (Seller - Pe) | NOT_ESTABLISHED |
| 177 | Industry(Buyer) | NOT_ESTABLISHED |
| 178 | Industry(Parent Of Target) | NOT_ESTABLISHED |
| 179 | Industry(Parent Of Buyer) | NOT_ESTABLISHED |
| 180 | Industry(Buyer - Pe) | NOT_ESTABLISHED |
| 181 | Industry(Seller - Pe) | NOT_ESTABLISHED |
| 182 | Sector(Target) | NOT_ESTABLISHED |
| 183 | Sector(Buyer) | NOT_ESTABLISHED |
| 184 | Sector(Parent Of Target) | NOT_ESTABLISHED |
| 185 | Sector(Parent Of Buyer) | NOT_ESTABLISHED |
| 186 | Sector(Buyer - Pe) | NOT_ESTABLISHED |
| 187 | Sector(Seller - Pe) | NOT_ESTABLISHED |
| 188 | Entity Description(Target) | NOT_ESTABLISHED |
| 189 | Entity Description(Buyer) | NOT_ESTABLISHED |
| 190 | Entity Description(Parent Of Target) | NOT_ESTABLISHED |
| 191 | Entity Description(Parent Of Buyer) | NOT_ESTABLISHED |
| 192 | % Deal Premium Vs 5D Prior Price | NOT_ESTABLISHED |
| 193 | % Deal Premium Vs 90D Prior Price | NOT_ESTABLISHED |
| 194 | % Deal Premium Vs 1D Prior Price | NOT_ESTABLISHED |
| 195 | % Deal Premium Vs 1Mth Prior Price | NOT_ESTABLISHED |
| 196 | % Deal Premium Vs 30D Prior Price | NOT_ESTABLISHED |
| 197 | % Deal Premium Vs 2Mths Prior Price | NOT_ESTABLISHED |
| 198 | % Deal Premium Vs 3Wks Prior Price | NOT_ESTABLISHED |
| 199 | % Deal Premium Vs 1Y Prior High Price | NOT_ESTABLISHED |
| 200 | % Deal Premium Vs 1Y Prior Low Price | NOT_ESTABLISHED |
| 201 | % Deal Premium Vs Unaffected Price | NOT_ESTABLISHED |
| 202 | Deal Ev / Book Value (X) | NOT_ESTABLISHED |
| 203 | Deal Ev / Net Income (X) | NOT_ESTABLISHED |
| 204 | Deal Ev/ Ebit (X) | NOT_ESTABLISHED |
| 205 | Deal Ev/ Ebitda (X) | NOT_ESTABLISHED |
| 206 | Deal Ev / Debt (X) | NOT_ESTABLISHED |
| 207 | Deal Ev / Revenue (X) | NOT_ESTABLISHED |
| 208 | Deal Price / Eps (X) | NOT_ESTABLISHED |
| 209 | Deal Price / Book Value (X) | NOT_ESTABLISHED |
| 210 | Deal Price / Ebit (X) | NOT_ESTABLISHED |
| 211 | Deal Price / Ebitda (X) | NOT_ESTABLISHED |
| 212 | Deal Price / Revenue (X) | NOT_ESTABLISHED |
| 213 | (Deal Price + Assumed Debt ) / Book Value (X) | NOT_ESTABLISHED |
| 214 | (Deal Price + Assumed Debt ) / Net Income (X) | NOT_ESTABLISHED |
| 215 | (Deal Price + Assumed Debt ) / Ebit (X) | NOT_ESTABLISHED |
| 216 | (Deal Price + Assumed Debt ) / Ebitda (X) | NOT_ESTABLISHED |
| 217 | (Deal Price + Assumed Debt ) / Revenue (X) | NOT_ESTABLISHED |
| 218 | Share Price (5Td Pre-Deal)(Target) | NOT_ESTABLISHED |
| 219 | Share Price (5Td Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 220 | Share Price (5Td Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 221 | Share Price (5Td Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 222 | Share Price (3Mths Pre-Deal)(Target) | NOT_ESTABLISHED |
| 223 | Share Price (3Mths Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 224 | Share Price (3Mths Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 225 | Share Price (3Mths Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 226 | Share Price (1Td Pre-Deal)(Target) | NOT_ESTABLISHED |
| 227 | Share Price (1Td Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 228 | Share Price (1Td Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 229 | Share Price (1Td Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 230 | Share Price (1Mth Pre-Deal)(Target) | NOT_ESTABLISHED |
| 231 | Share Price (1Mth Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 232 | Share Price (1Mth Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 233 | Share Price (1Mth Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 234 | Share Price (12Mth High Pre-Deal)(Target) | NOT_ESTABLISHED |
| 235 | Share Price (12Mth High Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 236 | Share Price (12Mth High Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 237 | Share Price (12Mth High Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 238 | Share Price (12Mth Low Pre-Deal)(Target) | NOT_ESTABLISHED |
| 239 | Share Price (12Mth Low Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 240 | Share Price (12Mth Low Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 241 | Share Price (12Mth Low Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 242 | Share Price (30D Pre-Deal)(Target) | NOT_ESTABLISHED |
| 243 | Share Price (30D Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 244 | Share Price (30D Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 245 | Share Price (30D Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 246 | Share Price (2Mths Pre-Deal)(Target) | NOT_ESTABLISHED |
| 247 | Share Price (2Mths Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 248 | Share Price (2Mths Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 249 | Share Price (2Mths Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 250 | Share Price (2Wks Pre-Deal)(Target) | NOT_ESTABLISHED |
| 251 | Share Price (2Wks Pre-Deal)(Buyer) | NOT_ESTABLISHED |
| 252 | Share Price (2Wks Pre-Deal)(Parent Of Target) | NOT_ESTABLISHED |
| 253 | Share Price (2Wks Pre-Deal)(Parent Of Buyer) | NOT_ESTABLISHED |
| 254 | Share Price - Unaffected Pre-Deal Date(Target) | date |
| 255 | Share Price - Unaffected Pre-Deal Date(Buyer) | date |
| 256 | Share Price - Unaffected Pre-Deal Date(Parent Of Target) | date |
| 257 | Share Price - Unaffected Pre-Deal(Target) | NOT_ESTABLISHED |
| 258 | Share Price - Unaffected Pre-Deal(Buyer) | NOT_ESTABLISHED |
| 259 | Share Price - Unaffected Pre-Deal(Parent Of Target) | NOT_ESTABLISHED |

## Section 5 — Funding fields (W1 col I: 35 fields)

Private-funding-round dataset (one record per round). Same caveats as Section 4.

| W1 row | field | units (from label) |
|--------|-------|--------------------|
| 2 | Announcement Date | date |
| 3 | Company Name | NOT_ESTABLISHED |
| 4 | Funding Type | NOT_ESTABLISHED |
| 5 | Amount Raised (Th) | thousands |
| 6 | Post-Money Valuation (Usd, Mn) | USD mn |
| 7 | Industry | NOT_ESTABLISHED |
| 8 | Country | NOT_ESTABLISHED |
| 9 | Company Description | NOT_ESTABLISHED |
| 10 | Funding Stage | NOT_ESTABLISHED |
| 11 | Revenue Range (Usd) | USD |
| 12 | Total Funding Amount, Funded Company (Usd, Mn) | USD mn |
| 13 | All Investor Names, Funded Company | NOT_ESTABLISHED |
| 14 | Crunchbase Categories | NOT_ESTABLISHED |
| 15 | City | NOT_ESTABLISHED |
| 16 | Company Type | NOT_ESTABLISHED |
| 17 | Exit Date | date |
| 18 | Founded Date | date |
| 19 | Headquarter Location | NOT_ESTABLISHED |
| 20 | Latest Funding Amount (Th) | thousands |
| 21 | Last Funding Round Date | date |
| 22 | Last Funding Type | NOT_ESTABLISHED |
| 23 | Lead Investor Names, Funded Company | NOT_ESTABLISHED |
| 24 | No. Of Employees | NOT_ESTABLISHED |
| 25 | No. Of Funding Rounds | NOT_ESTABLISHED |
| 26 | Operating Status | NOT_ESTABLISHED |
| 27 | No. Of Investors, Funded Company | NOT_ESTABLISHED |
| 28 | Closed Date | date |
| 29 | All Investor Names, Funding Round | NOT_ESTABLISHED |
| 30 | Lead Investor Name, Funding Round | NOT_ESTABLISHED |
| 31 | No. Of Lead Investors, Funding Round | NOT_ESTABLISHED |
| 32 | No. Of Investors, Funding Round | NOT_ESTABLISHED |
| 33 | Investment Stage | NOT_ESTABLISHED |
| 34 | Pre-Money Valuation (Usd, Mn) | USD mn |
| 35 | Funding Round Description | NOT_ESTABLISHED |
| 36 | Target Money Raised (Th) | thousands |

## Count reconciliation

| Section | Dictionary rows | Sheet count | Reconciles |
|---------|-----------------|-------------|------------|
| 1 Equity metrics | 513 | W1 Financial Metrics col A rows 2-514 = 513 | yes (1:1 by row) |
| 2 Consensus variants | 16 | W1 Available Consensus 176 metrics = 160 matched + 16 unmatched | yes (176-160) |
| 3 W2-only labels | 4 | W2 coded labels not in W1: FS 1, FP 2, TM 1 | yes |
| 4 M&A fields | 258 | W1 col G rows 2-259 = 258 | yes |
| 5 Funding fields | 35 | W1 col I rows 2-36 = 35 | yes |
| **Total** | **826** | | |

W2 coverage cross-check: FS coded rows 306, Ratios coded 104 + uncoded 14, Front Page 34, Trading Multiples 26 pairs (24 distinct codes). Every W2 coded label except the 4 in Section 3 appears in Section 1 via exact-name match; W1 cols D/E/F confirm the same crosswalk by formula.

