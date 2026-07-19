# W1 catalog — AlphaSense Financial Data Available Metrics with Consensus (v3)

Goal G012. Source: `inputs/data_templates/AlphaSense Financial Data Available Metrics with Consensus_v3.xlsx`
SHA-256: `9bf1cdeb4bfbaa924b395c31b2dc586d8039cc8873dfd6eca2aa4442b7ccf744`
Read-only evidence; workbook is git-ignored. Extraction: openpyxl 3.1.5, two passes (`data_only=True` for cached values, `data_only=False` for formulas).

Sheets: `Financial Metrics` (A1:I514, 514 rows x 9 cols), `Available Consensus` (A1:C177, 177 rows x 3 cols). No merged cells, no readable data validations.

## Sheet `Financial Metrics` — column semantics

| Col | Header (row 1) | Content | How populated |
|-----|----------------|---------|---------------|
| A | `Equity` | Metric display name; rows 2-514 = **513 metric rows** | static text |
| B | `Consensus Available?` | `Yes`/blank | formula `=IF(COUNTIF('Available Consensus'!A:A,A{r})=1,"Yes","")` (all 513 rows) |
| C | `Frequency?` | `Q`, `D/M`, `M`, `W`, `LTM`, `N/A` | static text |
| D | `FS Tab` | int or `#N/A` | formula `=MATCH(A{r},'[1]Financial Statements'!$C$8:$C$337,0)` — offset into an **external linked workbook** `[1]` whose `Financial Statements` sheet has exactly W2's shape (C8:C337); resolved sheet row = offset+7 |
| E | `Ratios Tab` | int or `#N/A` | formula `=MATCH(A{r},[1]Ratios!$C$8:$C$150,0)`; resolved row = offset+7 |
| F | `Front Page` | int or `#N/A` | formula `=MATCH(A{r},'[1]Front Page'!$C$7:$C$44,0)`; resolved row = offset+6 |
| G | `Mergers & Acquisitions` | independent field list, rows 2-259 = **258 fields** | static text |
| H | (blank) | empty spacer column | — |
| I | `Funding` | independent field list, rows 2-36 = **35 fields** | static text |

The `[1]` external reference proves W1 was built against a W2-style company template; the MATCH ranges (C8:C337, C8:C150, C7:C44) equal W2's exact sheet extents, so columns D/E/F are a provider-authored crosswalk from the metric list to the template tabs.

## Row-count reconciliation

- Sheet rows: 514 = 1 header + **513 metric rows** (column A, rows 2-514, no blanks).
- Frequency distribution (col C): `Q`=398, `D/M`=60, `N/A`=30, `M`=15, `W`=6, `LTM`=4 (sum 513 = 513).
- Consensus flag (col B): **164 rows = `Yes`**, 349 blank.
- `Available Consensus` sheet: 177 rows = 1 header + **176 consensus metrics**.
- Reconciliation 164 vs 176: 160 consensus names match col A exactly; 16 do not (listed below); 4 of the matched names are duplicated in col A (each duplicate row gets `Yes`): 160 + 4 = 164.
- Column A duplicate names (5): `Accrued and Deferred Income, Current`; `Common Equity Tier 1 Ratio, %`; `Net Interest Margin, %`; `Tier 1 Capital Ratio, %`; `Tier 2 Capital Ratio, %`.

### Consensus-sheet names with no exact col-A match (16)

| AC row | Consensus name | Nearest col-A variant |
|--------|----------------|----------------------|
| 4 | Adj. EBIT Margin, % | Adj. EBIT Margin %  (punctuation variant, W1 row 121) |
| 6 | Adj. EBITDA Margin, % | punctuation variant exists in col A |
| 8 | Adj. Net Income to Common Shareholders Margin, % | punctuation variant exists in col A |
| 47 | Net Interest Margin_2, % | `Net Interest Margin, %` (bank variant _2 not in col A) |
| 48 | Common Equity Tier 1 Ratio_2, % | `Common Equity Tier 1 Ratio, %` |
| 49 | Tier 1 Capital Ratio_2, % | `Tier 1 Capital Ratio, %` |
| 50 | Tier 2 Capital Ratio_2, % | `Tier 2 Capital Ratio, %` |
| 76 | LTM Dividend Payout Ratio, % | `LTM Dividend Payout Ratio (%)` (W1 row 390) |
| 121 | Unlevered FCF Margin, % | no exact match |
| 123 | SG&A Margin, % | no exact match (col A `SG&A Margin`-style variants) |
| 124 | R&D Margin, % | no exact match |
| 126 | Capex Margin, % | no exact match |
| 137 | Levered FCF Margin, % | no exact match |
| 138 | D&A Margin, % | no exact match |
| 139 | Gross Margin, % | no exact match |
| 165 | Dividend Yield, % | `Dividend Yield (%)` (W1 row 413) |

## Full metric inventory (`Financial Metrics` col A, rows 2-514)

Legend: FS/Ratio/FP = resolved W2 row (from cols D/E/F MATCH offsets); `-` = `#N/A` (metric not present on that W2 tab). Family is inferred from the sheet's contiguous row blocks (fundamentals rows 2-390, multiples 391-417, market data 418-469, consensus ratings/targets 470-484, descriptive 485-514).

| W1 row | Metric | Cons. | Freq | FS row | Ratios row | FrontPage row | Family |
|--------|--------|-------|------|--------|------------|---------------|--------|
| 2 | Revenue | Yes | Q | 8 | - | - | Fundamentals (financial statements & ratios) |
| 3 | Cost of Goods Sold |  | Q | 15 | - | - | Fundamentals (financial statements & ratios) |
| 4 | Gross Profit |  | Q | 18 | - | - | Fundamentals (financial statements & ratios) |
| 5 | EBIT | Yes | Q | 47 | - | - | Fundamentals (financial statements & ratios) |
| 6 | Revenue Adjustments |  | Q | 9 | - | - | Fundamentals (financial statements & ratios) |
| 7 | Adj. Revenue | Yes | Q | 10 | - | - | Fundamentals (financial statements & ratios) |
| 8 | Selling and Marketing Expense |  | Q | 22 | - | - | Fundamentals (financial statements & ratios) |
| 9 | General and Administrative Expense |  | Q | 23 | - | - | Fundamentals (financial statements & ratios) |
| 10 | Staff Costs |  | Q | 24 | - | - | Fundamentals (financial statements & ratios) |
| 11 | Selling, General and Administrative Expense |  | Q | 21 | - | - | Fundamentals (financial statements & ratios) |
| 12 | Research and Development Expense |  | Q | 31 | - | - | Fundamentals (financial statements & ratios) |
| 13 | Depreciation and Amortization Expense |  | Q | 42 | - | - | Fundamentals (financial statements & ratios) |
| 14 | Other Operating Expenses |  | Q | 34 | - | - | Fundamentals (financial statements & ratios) |
| 15 | EBIT Adjustments |  | Q | 48 | - | - | Fundamentals (financial statements & ratios) |
| 16 | Adj. EBIT | Yes | Q | 49 | - | - | Fundamentals (financial statements & ratios) |
| 17 | EBITDA | Yes | Q | 38 | - | - | Fundamentals (financial statements & ratios) |
| 18 | Adj. EBITDA | Yes | Q | 41 | - | - | Fundamentals (financial statements & ratios) |
| 19 | Interest Income |  | Q | 81 | - | - | Fundamentals (financial statements & ratios) |
| 20 | Interest Expense |  | Q | 95 | - | - | Fundamentals (financial statements & ratios) |
| 21 | Interest Income (Expense), Net |  | Q | 102 | - | - | Fundamentals (financial statements & ratios) |
| 22 | Other Non-Operating Income (Expense), Net |  | Q | 51 | - | - | Fundamentals (financial statements & ratios) |
| 23 | EBT |  | Q | 55 | - | - | Fundamentals (financial statements & ratios) |
| 24 | Tax Expense |  | Q | 58 | - | - | Fundamentals (financial statements & ratios) |
| 25 | Earnings from Equity Interest Net of Tax |  | Q | 66 | - | - | Fundamentals (financial statements & ratios) |
| 26 | Net Income from Continuous Operations |  | Q | 62 | - | - | Fundamentals (financial statements & ratios) |
| 27 | Net Income Discontinuous Operations |  | Q | 63 | - | - | Fundamentals (financial statements & ratios) |
| 28 | Net Income Extraordinary |  | Q | 64 | - | - | Fundamentals (financial statements & ratios) |
| 29 | Net Income from Tax Loss Carry Forward |  | Q | 65 | - | - | Fundamentals (financial statements & ratios) |
| 30 | Net Income to NCI |  | Q | 67 | - | - | Fundamentals (financial statements & ratios) |
| 31 | Preferred Stock Dividends and Other |  | Q | 68 | - | - | Fundamentals (financial statements & ratios) |
| 32 | Net Income to Common Shareholders | Yes | Q | 69 | - | - | Fundamentals (financial statements & ratios) |
| 33 | Net Income to Common Shareholder Adjustments |  | Q | 70 | - | - | Fundamentals (financial statements & ratios) |
| 34 | Adj. Net Income to Common Shareholders | Yes | Q | 71 | - | - | Fundamentals (financial statements & ratios) |
| 35 | Adjustments for Convertible Securities |  | Q | 72 | - | - | Fundamentals (financial statements & ratios) |
| 36 | Diluted Net Income to Common Shareholders |  | Q | 73 | - | - | Fundamentals (financial statements & ratios) |
| 37 | Earnings Per Share - WAB |  | Q | 74 | - | - | Fundamentals (financial statements & ratios) |
| 38 | Earnings Per Share - WAD | Yes | Q | 75 | - | - | Fundamentals (financial statements & ratios) |
| 39 | Adj. Earnings Per Share - WAD | Yes | Q | 76 | - | - | Fundamentals (financial statements & ratios) |
| 40 | Shares Outstanding - WAB |  | Q | 209 | - | - | Fundamentals (financial statements & ratios) |
| 41 | Shares Outstanding - WAD |  | Q | 210 | - | - | Fundamentals (financial statements & ratios) |
| 42 | Dividends Per Share | Yes | Q | 77 | - | - | Fundamentals (financial statements & ratios) |
| 43 | Gross Profit Adjustments |  | Q | 19 | - | - | Fundamentals (financial statements & ratios) |
| 44 | Adj. Gross Profit | Yes | Q | 20 | - | - | Fundamentals (financial statements & ratios) |
| 45 | Depreciation |  | Q | 43 | - | - | Fundamentals (financial statements & ratios) |
| 46 | Amortization |  | Q | 44 | - | - | Fundamentals (financial statements & ratios) |
| 47 | Add Back: D&A |  | Q | - | - | - | Fundamentals (financial statements & ratios) |
| 48 | EBITDA Adjustments |  | Q | 39 | - | - | Fundamentals (financial statements & ratios) |
| 49 | Cost of Goods Sold Adjustments |  | Q | 16 | - | - | Fundamentals (financial statements & ratios) |
| 50 | Adj. Cost of Goods Sold | Yes | Q | 17 | - | - | Fundamentals (financial statements & ratios) |
| 51 | Selling, General and Administrative Expense Adjustments |  | Q | 29 | - | - | Fundamentals (financial statements & ratios) |
| 52 | Adj. Selling, General and Administrative Expense | Yes | Q | 30 | - | - | Fundamentals (financial statements & ratios) |
| 53 | Research and Development Expense Adjustments |  | Q | 32 | - | - | Fundamentals (financial statements & ratios) |
| 54 | Adj. Research and Development Expense | Yes | Q | 33 | - | - | Fundamentals (financial statements & ratios) |
| 55 | Depreciation and Amortization Expense Adjustments |  | Q | 45 | - | - | Fundamentals (financial statements & ratios) |
| 56 | Adj. Depreciation and Amortization Expense | Yes | Q | 46 | - | - | Fundamentals (financial statements & ratios) |
| 57 | Other Operating Adjustments |  | Q | 35 | - | - | Fundamentals (financial statements & ratios) |
| 58 | Other Adjustments to EBITDA |  | Q | 40 | - | - | Fundamentals (financial statements & ratios) |
| 59 | Interest Income (Expense), Net Adjustments |  | Q | 103 | - | - | Fundamentals (financial statements & ratios) |
| 60 | Adj. Interest Income (Expense), Net | Yes | Q | 104 | - | - | Fundamentals (financial statements & ratios) |
| 61 | Other Non-Operating Adjustments |  | Q | 52 | - | - | Fundamentals (financial statements & ratios) |
| 62 | EBT Adjustments |  | Q | 56 | - | - | Fundamentals (financial statements & ratios) |
| 63 | Adj. EBT | Yes | Q | 57 | - | - | Fundamentals (financial statements & ratios) |
| 64 | Tax Expense Adjustments |  | Q | 59 | - | - | Fundamentals (financial statements & ratios) |
| 65 | Adj. Tax Expense | Yes | Q | 60 | - | - | Fundamentals (financial statements & ratios) |
| 66 | Effective Tax Rate_2 | Yes | Q | - | - | - | Fundamentals (financial statements & ratios) |
| 67 | Funds From Operations (FFO) | Yes | Q | 249 | - | - | Fundamentals (financial statements & ratios) |
| 68 | Funds From Operations Per Share | Yes | Q | 250 | - | - | Fundamentals (financial statements & ratios) |
| 69 | Net Premiums Written | Yes | Q | 110 | - | - | Fundamentals (financial statements & ratios) |
| 70 | Change in Net Unearned Premium Reserves |  | Q | 111 | - | - | Fundamentals (financial statements & ratios) |
| 71 | Net Earned Premiums | Yes | Q | 112 | - | - | Fundamentals (financial statements & ratios) |
| 72 | Net Investment Income |  | Q | 92 | - | - | Fundamentals (financial statements & ratios) |
| 73 | Net Investment Gains |  | Q | 93 | - | - | Fundamentals (financial statements & ratios) |
| 74 | Interest Revenue |  | Q | 80 | - | - | Fundamentals (financial statements & ratios) |
| 75 | Net Foreign Exchange Gain/Loss |  | Q | 54 | - | - | Fundamentals (financial statements & ratios) |
| 76 | Fees and Commissions |  | Q | 86 | - | - | Fundamentals (financial statements & ratios) |
| 77 | Other Income Expense |  | Q | 50 | - | - | Fundamentals (financial statements & ratios) |
| 78 | Loss & Loss Adjustment Expenses |  | Q | 113 | - | - | Fundamentals (financial statements & ratios) |
| 79 | Policyholder Interest |  | Q | 114 | - | - | Fundamentals (financial statements & ratios) |
| 80 | Policyholder Dividends |  | Q | 116 | - | - | Fundamentals (financial statements & ratios) |
| 81 | Policy Acquisition Expenses |  | Q | - | - | - | Fundamentals (financial statements & ratios) |
| 82 | Underwriting Expenses |  | Q | 115 | - | - | Fundamentals (financial statements & ratios) |
| 83 | Fees and Commission Expense |  | Q | 100 | - | - | Fundamentals (financial statements & ratios) |
| 84 | Change in Insurance Liabilities Net of Reinsurance |  | Q | 311 | - | - | Fundamentals (financial statements & ratios) |
| 85 | Change in Investment Contract |  | Q | 312 | - | - | Fundamentals (financial statements & ratios) |
| 86 | Gross Premiums Written |  | Q | 108 | - | - | Fundamentals (financial statements & ratios) |
| 87 | Ceded Premiums |  | Q | 109 | - | - | Fundamentals (financial statements & ratios) |
| 88 | Adjusted Funds From Operations (FFO) | Yes | Q | 251 | - | - | Fundamentals (financial statements & ratios) |
| 89 | Adjusted Funds From Operations Per Share | Yes | Q | 252 | - | - | Fundamentals (financial statements & ratios) |
| 90 | Interest Income from Loans and Leases |  | Q | 82 | - | - | Fundamentals (financial statements & ratios) |
| 91 | Interest Income from Securities |  | Q | 83 | - | - | Fundamentals (financial statements & ratios) |
| 92 | Interest Income from Deposits |  | Q | 84 | - | - | Fundamentals (financial statements & ratios) |
| 93 | Other Interest Income |  | Q | 85 | - | - | Fundamentals (financial statements & ratios) |
| 94 | Interest Expense for Deposit |  | Q | 96 | - | - | Fundamentals (financial statements & ratios) |
| 95 | Interest Expense for LTD and Capital Securities |  | Q | 97 | - | - | Fundamentals (financial statements & ratios) |
| 96 | Other Interest Expense |  | Q | 98 | - | - | Fundamentals (financial statements & ratios) |
| 97 | Net Interest Income | Yes | Q | 101 | - | - | Fundamentals (financial statements & ratios) |
| 98 | Dividend Income |  | Q | 12 | - | - | Fundamentals (financial statements & ratios) |
| 99 | Net Trading Income |  | Q | 87 | - | - | Fundamentals (financial statements & ratios) |
| 100 | Investment Banking Profit | Yes | Q | 91 | - | - | Fundamentals (financial statements & ratios) |
| 101 | Trading Gain/Loss |  | Q | 88 | - | - | Fundamentals (financial statements & ratios) |
| 102 | Gain/Loss on Investments |  | Q | 89 | - | - | Fundamentals (financial statements & ratios) |
| 103 | Gain/Loss on Derivatives |  | Q | 90 | - | - | Fundamentals (financial statements & ratios) |
| 104 | Other Non-Interest Revenue |  | Q | 14 | - | - | Fundamentals (financial statements & ratios) |
| 105 | Non-Interest Revenue | Yes | Q | 13 | - | - | Fundamentals (financial statements & ratios) |
| 106 | Provision for Credit Losses |  | Q | 99 | - | - | Fundamentals (financial statements & ratios) |
| 107 | Other Non-Interest Expense |  | Q | 36 | - | - | Fundamentals (financial statements & ratios) |
| 108 | Total Non-Interest Expense | Yes | Q | 37 | - | - | Fundamentals (financial statements & ratios) |
| 109 | Income from Associates and Other Participating Interests |  | Q | 94 | - | - | Fundamentals (financial statements & ratios) |
| 110 | Special Income Charges |  | Q | 53 | - | - | Fundamentals (financial statements & ratios) |
| 111 | Other Revenue |  | Q | 11 | - | - | Fundamentals (financial statements & ratios) |
| 112 | Compensation Expense | Yes | Q | 25 | - | - | Fundamentals (financial statements & ratios) |
| 113 | Occupancy and Equipment Expense | Yes | Q | 26 | - | - | Fundamentals (financial statements & ratios) |
| 114 | Professional Expenses |  | Q | 27 | - | - | Fundamentals (financial statements & ratios) |
| 115 | Other SG&A Expenses |  | Q | 28 | - | - | Fundamentals (financial statements & ratios) |
| 116 | Amortization of Securities |  | Q | 105 | - | - | Fundamentals (financial statements & ratios) |
| 117 | Total Assets | Yes | Q | 143 | - | - | Fundamentals (financial statements & ratios) |
| 118 | Cash and Cash Equivalents and Short Term Investments | Yes | Q | 123 | - | - | Fundamentals (financial statements & ratios) |
| 119 | Receivables, Net | Yes | Q | 125 | - | - | Fundamentals (financial statements & ratios) |
| 120 | Total Inventory, Net | Yes | Q | 128 | - | - | Fundamentals (financial statements & ratios) |
| 121 | Total Current Assets | Yes | Q | 131 | - | - | Fundamentals (financial statements & ratios) |
| 122 | PP&E, Net | Yes | Q | 132 | - | - | Fundamentals (financial statements & ratios) |
| 123 | Intangible Assets (Incl. Goodwill) | Yes | Q | 135 | - | - | Fundamentals (financial statements & ratios) |
| 124 | Total Non-Current Assets | Yes | Q | 142 | - | - | Fundamentals (financial statements & ratios) |
| 125 | Accounts Payable and Current Accrued Expenses | Yes | Q | 146 | - | - | Fundamentals (financial statements & ratios) |
| 126 | Total Debt and Lease Obligation | Yes | Q | 179 | - | - | Fundamentals (financial statements & ratios) |
| 127 | Net Debt | Yes | Q | 181 | - | - | Fundamentals (financial statements & ratios) |
| 128 | Current Debt and Lease Obligation | Yes | Q | 154 | - | - | Fundamentals (financial statements & ratios) |
| 129 | Total Current Liabilities | Yes | Q | 164 | - | - | Fundamentals (financial statements & ratios) |
| 130 | Long Term Debt and Lease Obligation | Yes | Q | 167 | - | - | Fundamentals (financial statements & ratios) |
| 131 | Total Non-Current Liabilities | Yes | Q | 176 | - | - | Fundamentals (financial statements & ratios) |
| 132 | Total Liabilities | Yes | Q | 185 | - | - | Fundamentals (financial statements & ratios) |
| 133 | Total Stockholders Equity | Yes | Q | 199 | - | - | Fundamentals (financial statements & ratios) |
| 134 | Total Stockholders Equity including Minority Interest | Yes | Q | 200 | - | - | Fundamentals (financial statements & ratios) |
| 135 | Total Liabilities and Stockholders Equity | Yes | Q | 201 | - | - | Fundamentals (financial statements & ratios) |
| 136 | Other Current Assets |  | Q | 130 | - | - | Fundamentals (financial statements & ratios) |
| 137 | Goodwill |  | Q | 133 | - | - | Fundamentals (financial statements & ratios) |
| 138 | Intangible Assets (Excl. Goodwill) |  | Q | 134 | - | - | Fundamentals (financial statements & ratios) |
| 139 | Other Non-Current Assets |  | Q | 140 | - | - | Fundamentals (financial statements & ratios) |
| 140 | Payables | Yes | Q | 148 | - | - | Fundamentals (financial statements & ratios) |
| 141 | Current Accrued Expenses |  | Q | 150 | - | - | Fundamentals (financial statements & ratios) |
| 142 | Current Debt |  | Q | 152 | - | - | Fundamentals (financial statements & ratios) |
| 143 | Current Lease Obligation |  | Q | 153 | - | - | Fundamentals (financial statements & ratios) |
| 144 | Current Deferred Taxes Liabilities |  | Q | 157 | - | - | Fundamentals (financial statements & ratios) |
| 145 | Current Deferred Revenue |  | Q | 155 | - | - | Fundamentals (financial statements & ratios) |
| 146 | Current Deferred Liabilities |  | Q | 156 | - | - | Fundamentals (financial statements & ratios) |
| 147 | Current Provisions |  | Q | 160 | - | - | Fundamentals (financial statements & ratios) |
| 148 | Other Current Liabilities |  | Q | 163 | - | - | Fundamentals (financial statements & ratios) |
| 149 | Long Term Debt |  | Q | 165 | - | - | Fundamentals (financial statements & ratios) |
| 150 | Long Term Lease Obligation |  | Q | 166 | - | - | Fundamentals (financial statements & ratios) |
| 151 | Long Term Provisions |  | Q | 168 | - | - | Fundamentals (financial statements & ratios) |
| 152 | Non-Current Deferred Taxes Liabilities |  | Q | 171 | - | - | Fundamentals (financial statements & ratios) |
| 153 | Non-Current Deferred Revenue |  | Q | 169 | - | - | Fundamentals (financial statements & ratios) |
| 154 | Non-Current Deferred Liabilities |  | Q | 170 | - | - | Fundamentals (financial statements & ratios) |
| 155 | Non-Current Pension and Other Post Retirement Benefit Plans |  | Q | 173 | - | - | Fundamentals (financial statements & ratios) |
| 156 | Non-Current Accrued Expenses |  | Q | 174 | - | - | Fundamentals (financial statements & ratios) |
| 157 | Other Non-Current Liabilities |  | Q | 175 | - | - | Fundamentals (financial statements & ratios) |
| 158 | Share Capital |  | Q | 187 | - | - | Fundamentals (financial statements & ratios) |
| 159 | Additional Paid-In Capital |  | Q | 191 | - | - | Fundamentals (financial statements & ratios) |
| 160 | Share and Additional Paid-In Capital | Yes | Q | 192 | - | - | Fundamentals (financial statements & ratios) |
| 161 | Retained Earnings | Yes | Q | 193 | - | - | Fundamentals (financial statements & ratios) |
| 162 | Treasury Stock | Yes | Q | 194 | - | - | Fundamentals (financial statements & ratios) |
| 163 | Other Comprehensive Income |  | Q | 195 | - | - | Fundamentals (financial statements & ratios) |
| 164 | Other Equity Interest |  | Q | 196 | - | - | Fundamentals (financial statements & ratios) |
| 165 | Minority Interest | Yes | Q | 197 | - | - | Fundamentals (financial statements & ratios) |
| 166 | Net Working Capital |  | Q | 204 | - | - | Fundamentals (financial statements & ratios) |
| 167 | Cash and Cash Equivalents |  | Q | 121 | - | - | Fundamentals (financial statements & ratios) |
| 168 | Short Term Investments |  | Q | 122 | - | - | Fundamentals (financial statements & ratios) |
| 169 | Other Payable |  | Q | 149 | - | - | Fundamentals (financial statements & ratios) |
| 170 | Pension and Other Post Retirement Benefit Plans |  | Q | 161 | - | - | Fundamentals (financial statements & ratios) |
| 171 | Accrued and Deferred Income, Current |  | Q | 159 | - | - | Fundamentals (financial statements & ratios) |
| 172 | Accrued and Deferred Income, Non-Current |  | Q | 172 | - | - | Fundamentals (financial statements & ratios) |
| 173 | Other Debt/(Cash)Items |  | Q | 180 | - | - | Fundamentals (financial statements & ratios) |
| 174 | Tangible Book Value per Share | Yes | Q | 208 | - | - | Fundamentals (financial statements & ratios) |
| 175 | Book Value per Share | Yes | Q | 206 | - | - | Fundamentals (financial statements & ratios) |
| 176 | Minority Interest and Preferred Stock |  | Q | 198 | - | - | Fundamentals (financial statements & ratios) |
| 177 | Accounts Receivable |  | Q | 126 | - | - | Fundamentals (financial statements & ratios) |
| 178 | Other Receivables |  | Q | 127 | - | - | Fundamentals (financial statements & ratios) |
| 179 | Accounts Payable |  | Q | 147 | - | - | Fundamentals (financial statements & ratios) |
| 180 | Common Stock |  | Q | 188 | - | - | Fundamentals (financial statements & ratios) |
| 181 | Preferred Stock |  | Q | 189 | - | - | Fundamentals (financial statements & ratios) |
| 182 | Other Share Capital |  | Q | 190 | - | - | Fundamentals (financial statements & ratios) |
| 183 | Net Loan | Yes | Q | 222 | - | - | Fundamentals (financial statements & ratios) |
| 184 | Long Term Equity Investment |  | Q | 137 | - | - | Fundamentals (financial statements & ratios) |
| 185 | Other Invested Assets |  | Q | 138 | - | - | Fundamentals (financial statements & ratios) |
| 186 | Total Investments |  | Q | 136 | - | - | Fundamentals (financial statements & ratios) |
| 187 | Deferred Policy Acquisition Costs |  | Q | 232 | - | - | Fundamentals (financial statements & ratios) |
| 188 | Other Assets |  | Q | 141 | - | - | Fundamentals (financial statements & ratios) |
| 189 | Total Policyholder Liabilities |  | Q | 235 | - | - | Fundamentals (financial statements & ratios) |
| 190 | Unpaid Loss and Loss Reserve |  | Q | 236 | - | - | Fundamentals (financial statements & ratios) |
| 191 | Unearned Premiums |  | Q | 237 | - | - | Fundamentals (financial statements & ratios) |
| 192 | Future Policy Benefits |  | Q | 238 | - | - | Fundamentals (financial statements & ratios) |
| 193 | Policyholder Funds |  | Q | 239 | - | - | Fundamentals (financial statements & ratios) |
| 194 | Total Deposits | Yes | Q | 225 | - | - | Fundamentals (financial statements & ratios) |
| 195 | Other Liabilities |  | Q | 184 | - | - | Fundamentals (financial statements & ratios) |
| 196 | Investment in Financial Assets |  | Q | 223 | - | - | Fundamentals (financial statements & ratios) |
| 197 | Reinsurance Assets |  | Q | 233 | - | - | Fundamentals (financial statements & ratios) |
| 198 | Insurance Contract Liabilities |  | Q | 240 | - | - | Fundamentals (financial statements & ratios) |
| 199 | Investment Contract Liabilities |  | Q | 241 | - | - | Fundamentals (financial statements & ratios) |
| 200 | Reinsurance Liabilities |  | Q | 242 | - | - | Fundamentals (financial statements & ratios) |
| 201 | Tangible Book Value | Yes | Q | 207 | - | - | Fundamentals (financial statements & ratios) |
| 202 | Book Value | Yes | Q | 205 | - | - | Fundamentals (financial statements & ratios) |
| 203 | Total Share Count (EoP) | Yes | Q | 211 | - | - | Fundamentals (financial statements & ratios) |
| 204 | Restricted Cash and Investments |  | Q | 124 | - | - | Fundamentals (financial statements & ratios) |
| 205 | Federal Funds Sold |  | Q | 215 | - | - | Fundamentals (financial statements & ratios) |
| 206 | Total Lease Obligation |  | Q | 178 | - | - | Fundamentals (financial statements & ratios) |
| 207 | Cash and Cash Equivalents and Federal Funds Sold |  | Q | 216 | - | - | Fundamentals (financial statements & ratios) |
| 208 | Securities and Investments |  | Q | 217 | - | - | Fundamentals (financial statements & ratios) |
| 209 | Security Borrowed |  | Q | 218 | - | - | Fundamentals (financial statements & ratios) |
| 210 | Gross Loan | Yes | Q | 219 | - | - | Fundamentals (financial statements & ratios) |
| 211 | Allowance for Loans and Lease Losses | Yes | Q | 220 | - | - | Fundamentals (financial statements & ratios) |
| 212 | Unearned Income |  | Q | 221 | - | - | Fundamentals (financial statements & ratios) |
| 213 | Interest Bearing Deposits Liabilities | Yes | Q | 226 | - | - | Fundamentals (financial statements & ratios) |
| 214 | Non Interest Bearing Deposits | Yes | Q | 227 | - | - | Fundamentals (financial statements & ratios) |
| 215 | Securities Loaned |  | Q | 228 | - | - | Fundamentals (financial statements & ratios) |
| 216 | Trading Liabilities |  | Q | 162 | - | - | Fundamentals (financial statements & ratios) |
| 217 | Deferred Tax Assets | Yes | Q | 139 | - | - | Fundamentals (financial statements & ratios) |
| 218 | Current Tax Assets |  | Q | 129 | - | - | Fundamentals (financial statements & ratios) |
| 219 | Accrued Expenses | Yes | Q | 151 | - | - | Fundamentals (financial statements & ratios) |
| 220 | Deferred Income |  | Q | 158 | - | - | Fundamentals (financial statements & ratios) |
| 221 | Accrued and Deferred Income, Current |  | Q | 159 | - | - | Fundamentals (financial statements & ratios) |
| 222 | Total Debt  |  | Q | 177 | - | - | Fundamentals (financial statements & ratios) |
| 223 | Provisions |  | Q | 182 | - | - | Fundamentals (financial statements & ratios) |
| 224 | Deferred Tax Liabilities | Yes | Q | 183 | - | - | Fundamentals (financial statements & ratios) |
| 225 | Net Interest Margin, % | Yes | Q | - | 85 | - | Fundamentals (financial statements & ratios) |
| 226 | Common Equity Tier 1 Ratio, % | Yes | Q | - | 82 | - | Fundamentals (financial statements & ratios) |
| 227 | Tier 1 Capital Ratio, % | Yes | Q | - | 83 | - | Fundamentals (financial statements & ratios) |
| 228 | Tier 2 Capital Ratio, % | Yes | Q | - | 84 | - | Fundamentals (financial statements & ratios) |
| 229 | Net Income (Loss) From Continuing Operations (CF) | Yes | Q | 247 | - | - | Fundamentals (financial statements & ratios) |
| 230 | Change in Working Capital |  | Q | 248 | - | - | Fundamentals (financial statements & ratios) |
| 231 | Operating Cash Flow | Yes | Q | 245 | - | - | Fundamentals (financial statements & ratios) |
| 232 | Capex | Yes | Q | 278 | - | - | Fundamentals (financial statements & ratios) |
| 233 | Investing Cash Flow | Yes | Q | 277 | - | - | Fundamentals (financial statements & ratios) |
| 234 | Increase/(Decrease) in Debt, Net | Yes | Q | 293 | - | - | Fundamentals (financial statements & ratios) |
| 235 | Payment of Dividends |  | Q | 294 | - | - | Fundamentals (financial statements & ratios) |
| 236 | Financing Cash Flow | Yes | Q | 292 | - | - | Fundamentals (financial statements & ratios) |
| 237 | Cash and Cash Equivalents - Beginning Balance | Yes | Q | 307 | - | - | Fundamentals (financial statements & ratios) |
| 238 | Cash and Cash Equivalents - Ending Balance | Yes | Q | 308 | - | - | Fundamentals (financial statements & ratios) |
| 239 | Depreciation and Amortization | Yes | Q | 253 | - | - | Fundamentals (financial statements & ratios) |
| 240 | Stock Based Compensation | Yes | Q | 254 | - | - | Fundamentals (financial statements & ratios) |
| 241 | Receipts from Customers |  | Q | 263 | - | - | Fundamentals (financial statements & ratios) |
| 242 | Receipts from Government Grants |  | Q | 264 | - | - | Fundamentals (financial statements & ratios) |
| 243 | Other Cash Receipts |  | Q | 265 | - | - | Fundamentals (financial statements & ratios) |
| 244 | Classes of Cash Receipts (Operating Activities) |  | Q | 266 | - | - | Fundamentals (financial statements & ratios) |
| 245 | Payments to Suppliers for Goods and Services |  | Q | 267 | - | - | Fundamentals (financial statements & ratios) |
| 246 | Payments on Behalf of Employees |  | Q | 268 | - | - | Fundamentals (financial statements & ratios) |
| 247 | Other Cash Payments |  | Q | 269 | - | - | Fundamentals (financial statements & ratios) |
| 248 | Classes of Cash Payments (Operating Activities) |  | Q | 270 | - | - | Fundamentals (financial statements & ratios) |
| 249 | Dividends Paid-Direct |  | Q | 271 | - | - | Fundamentals (financial statements & ratios) |
| 250 | Dividends Received-Direct |  | Q | 272 | - | - | Fundamentals (financial statements & ratios) |
| 251 | Interest Paid-Direct |  | Q | 273 | - | - | Fundamentals (financial statements & ratios) |
| 252 | Interest Received-Direct |  | Q | 274 | - | - | Fundamentals (financial statements & ratios) |
| 253 | Taxes Refund Paid-Direct |  | Q | 275 | - | - | Fundamentals (financial statements & ratios) |
| 254 | Deferred Tax |  | Q | 255 | - | - | Fundamentals (financial statements & ratios) |
| 255 | Other Non-Cash Adjustments |  | Q | 256 | - | - | Fundamentals (financial statements & ratios) |
| 256 | Change in Receivables |  | Q | 257 | - | - | Fundamentals (financial statements & ratios) |
| 257 | Change in Inventories |  | Q | 258 | - | - | Fundamentals (financial statements & ratios) |
| 258 | Change in Prepaid Assets |  | Q | 259 | - | - | Fundamentals (financial statements & ratios) |
| 259 | Change in Payable |  | Q | 260 | - | - | Fundamentals (financial statements & ratios) |
| 260 | Change in Accrued Expense |  | Q | 261 | - | - | Fundamentals (financial statements & ratios) |
| 261 | Other Changes in Working Capital |  | Q | 262 | - | - | Fundamentals (financial statements & ratios) |
| 262 | Purchase of PP&E |  | Q | 279 | - | - | Fundamentals (financial statements & ratios) |
| 263 | Sale of PP&E |  | Q | 280 | - | - | Fundamentals (financial statements & ratios) |
| 264 | PPE Purchase and Sale, Net |  | Q | 281 | - | - | Fundamentals (financial statements & ratios) |
| 265 | Purchase of Intangibles |  | Q | 282 | - | - | Fundamentals (financial statements & ratios) |
| 266 | Sale of Intangibles |  | Q | 283 | - | - | Fundamentals (financial statements & ratios) |
| 267 | Intangibles Purchase and Sale, Net |  | Q | 284 | - | - | Fundamentals (financial statements & ratios) |
| 268 | Acquisitons |  | Q | 285 | - | - | Fundamentals (financial statements & ratios) |
| 269 | Divestitures |  | Q | 286 | - | - | Fundamentals (financial statements & ratios) |
| 270 | Acquisitions/Divestitures, Net |  | Q | 287 | - | - | Fundamentals (financial statements & ratios) |
| 271 | Purchase of Investment |  | Q | 288 | - | - | Fundamentals (financial statements & ratios) |
| 272 | Sale of Investment |  | Q | 289 | - | - | Fundamentals (financial statements & ratios) |
| 273 | Investments Purchase and Sale, Net |  | Q | 290 | - | - | Fundamentals (financial statements & ratios) |
| 274 | Other Investing Cash Flow |  | Q | 291 | - | - | Fundamentals (financial statements & ratios) |
| 275 | Common Stock Issuance, Net |  | Q | 295 | - | - | Fundamentals (financial statements & ratios) |
| 276 | Preferred Stock Issuance, Net |  | Q | 296 | - | - | Fundamentals (financial statements & ratios) |
| 277 | Proceeds from Stock Option Exercised |  | Q | 297 | - | - | Fundamentals (financial statements & ratios) |
| 278 | Other Financing Cash Flow |  | Q | 298 | - | - | Fundamentals (financial statements & ratios) |
| 279 | Changes in Cash |  | Q | 305 | - | - | Fundamentals (financial statements & ratios) |
| 280 | Effect of Exchange Rate on Cash and Cash Equivalents |  | Q | 309 | - | - | Fundamentals (financial statements & ratios) |
| 281 | Other Cash Adjustments Outside Change in Cash |  | Q | 310 | - | - | Fundamentals (financial statements & ratios) |
| 282 | Free Cash Flow | Yes | Q | 302 | - | - | Fundamentals (financial statements & ratios) |
| 283 | Free Cash Flow per Share | Yes | Q | 303 | - | - | Fundamentals (financial statements & ratios) |
| 284 | Increase/(decrease) in Cash and Cash Equivalents | Yes | Q | 306 | - | - | Fundamentals (financial statements & ratios) |
| 285 | Interest Credited on Policyholder Deposits |  | Q | 313 | - | - | Fundamentals (financial statements & ratios) |
| 286 | Change in Loss and Loss Adjustment Expense Reserves |  | Q | 314 | - | - | Fundamentals (financial statements & ratios) |
| 287 | Change in Unearned Premiums |  | Q | 315 | - | - | Fundamentals (financial statements & ratios) |
| 288 | Change in Deferred Acquisition Costs |  | Q | 316 | - | - | Fundamentals (financial statements & ratios) |
| 289 | Proceeds from Loans |  | Q | 299 | - | - | Fundamentals (financial statements & ratios) |
| 290 | Payment for Loans |  | Q | 300 | - | - | Fundamentals (financial statements & ratios) |
| 291 | Loan Proceeds and Payment, Net |  | Q | 301 | - | - | Fundamentals (financial statements & ratios) |
| 292 | Increase/(Decrease) in Deposit |  | Q | 317 | - | - | Fundamentals (financial statements & ratios) |
| 293 | Cash Received from Insurance Activities |  | Q | 318 | - | - | Fundamentals (financial statements & ratios) |
| 294 | Cash Receipts from Tax Refunds |  | Q | 319 | - | - | Fundamentals (financial statements & ratios) |
| 295 | Cash Paid for Insurance Activities |  | Q | 320 | - | - | Fundamentals (financial statements & ratios) |
| 296 | All Taxes Paid |  | Q | 276 | - | - | Fundamentals (financial statements & ratios) |
| 297 | Change in Insurance Contract Assets |  | Q | 321 | - | - | Fundamentals (financial statements & ratios) |
| 298 | Change in Reinsurance Receivables |  | Q | 322 | - | - | Fundamentals (financial statements & ratios) |
| 299 | Operating Gains Losses |  | Q | 334 | - | - | Fundamentals (financial statements & ratios) |
| 300 | Provision for Loan Lease and Other Losses |  | Q | 335 | - | - | Fundamentals (financial statements & ratios) |
| 301 | Provision and Write-Off of Assets |  | Q | 336 | - | - | Fundamentals (financial statements & ratios) |
| 302 | Change in Loans |  | Q | 323 | - | - | Fundamentals (financial statements & ratios) |
| 303 | Change in Financial Assets |  | Q | 324 | - | - | Fundamentals (financial statements & ratios) |
| 304 | Change in Deposits by Banks and Customers |  | Q | 325 | - | - | Fundamentals (financial statements & ratios) |
| 305 | Change in Financial Liabilities |  | Q | 326 | - | - | Fundamentals (financial statements & ratios) |
| 306 | Cash Receipts from Deposits by Banks and Customers |  | Q | 327 | - | - | Fundamentals (financial statements & ratios) |
| 307 | Cash Receipts from Loans |  | Q | 328 | - | - | Fundamentals (financial statements & ratios) |
| 308 | Cash Receipts from Securities Related Activities |  | Q | 329 | - | - | Fundamentals (financial statements & ratios) |
| 309 | Cash Receipts from Fees and Commissions |  | Q | 330 | - | - | Fundamentals (financial statements & ratios) |
| 310 | Cash Payments for Deposits by Banks and Customers |  | Q | 331 | - | - | Fundamentals (financial statements & ratios) |
| 311 | Cash Payments for Loans |  | Q | 332 | - | - | Fundamentals (financial statements & ratios) |
| 312 | Interest and Commission Paid |  | Q | 333 | - | - | Fundamentals (financial statements & ratios) |
| 313 | Unlevered FCF |  | Q | 304 | - | - | Fundamentals (financial statements & ratios) |
| 314 | Operating Cash Flow before WC |  | Q | 246 | - | - | Fundamentals (financial statements & ratios) |
| 315 | Return on Equity | Yes | Q | - | 90 | - | Fundamentals (financial statements & ratios) |
| 316 | Return on Invested Capital | Yes | Q | - | 91 | - | Fundamentals (financial statements & ratios) |
| 317 | Return on Assets | Yes | Q | - | 92 | - | Fundamentals (financial statements & ratios) |
| 318 | Return on Capital Employed | Yes | Q | - | 93 | - | Fundamentals (financial statements & ratios) |
| 319 | Net Interest Margin, % | Yes | Q | - | 85 | - | Fundamentals (financial statements & ratios) |
| 320 | Gross Margin (%) |  | Q | - | 8 | - | Fundamentals (financial statements & ratios) |
| 321 | SG&A Margin (%) |  | Q | - | 10 | - | Fundamentals (financial statements & ratios) |
| 322 | R&D Margin (%) |  | Q | - | 12 | - | Fundamentals (financial statements & ratios) |
| 323 | D&A Margin (%) |  | Q | - | 14 | - | Fundamentals (financial statements & ratios) |
| 324 | SBC Margin (%) |  | Q | - | 16 | - | Fundamentals (financial statements & ratios) |
| 325 | EBIT Margin, % | Yes | Q | - | 17 | - | Fundamentals (financial statements & ratios) |
| 326 | EBITDA Margin, % | Yes | Q | - | 19 | - | Fundamentals (financial statements & ratios) |
| 327 | Net Income to Common Shareholders Margin, % | Yes | Q | - | 22 | - | Fundamentals (financial statements & ratios) |
| 328 | Effective Tax Rate | Yes | Q | 61 | 21 | - | Fundamentals (financial statements & ratios) |
| 329 | CapEx Margin (%) |  | Q | - | 25 | - | Fundamentals (financial statements & ratios) |
| 330 | Unlevered FCF Margin (%) |  | Q | - | 27 | - | Fundamentals (financial statements & ratios) |
| 331 | Levered FCF Margin (%) |  | Q | - | 26 | - | Fundamentals (financial statements & ratios) |
| 332 | FCF/Net Income to Common Shareholders Margin, % | Yes | Q | - | 24 | - | Fundamentals (financial statements & ratios) |
| 333 | Loss Ratio, % |  | Q | - | 96 | - | Fundamentals (financial statements & ratios) |
| 334 | Expense Ratio, % |  | Q | - | 97 | - | Fundamentals (financial statements & ratios) |
| 335 | Combined Ratio, % |  | Q | - | 98 | - | Fundamentals (financial statements & ratios) |
| 336 | Efficiency Ratio, % | Yes | Q | - | 87 | - | Fundamentals (financial statements & ratios) |
| 337 | Cost to Income Ratio, % | Yes | Q | - | 86 | - | Fundamentals (financial statements & ratios) |
| 338 | Common Equity Tier 1 Ratio, % | Yes | Q | - | 82 | - | Fundamentals (financial statements & ratios) |
| 339 | Tier 1 Capital Ratio, % | Yes | Q | - | 83 | - | Fundamentals (financial statements & ratios) |
| 340 | Tier 2 Capital Ratio, % | Yes | Q | - | 84 | - | Fundamentals (financial statements & ratios) |
| 341 | Provision for Credit Losses Margin, % | Yes | Q | - | 101 | - | Fundamentals (financial statements & ratios) |
| 342 | Compensation Expense Margin, % |  | Q | - | 102 | - | Fundamentals (financial statements & ratios) |
| 343 | Occupancy and Equipment Expense Margin, % |  | Q | - | 103 | - | Fundamentals (financial statements & ratios) |
| 344 | Professional Expenses Margin, % |  | Q | - | 104 | - | Fundamentals (financial statements & ratios) |
| 345 | Adj. Gross Margin, % | Yes | Q | - | 9 | - | Fundamentals (financial statements & ratios) |
| 346 | Adj. EBIT Margin (%) |  | Q | - | 18 | - | Fundamentals (financial statements & ratios) |
| 347 | Adj. EBITDA Margin (%) |  | Q | - | 20 | - | Fundamentals (financial statements & ratios) |
| 348 | Adj. Net Income to Common Shareholders Margin (%) |  | Q | - | 23 | - | Fundamentals (financial statements & ratios) |
| 349 | Adj. SG&A Margin, % | Yes | Q | - | 11 | - | Fundamentals (financial statements & ratios) |
| 350 | Adj. R&D Margin, % | Yes | Q | - | 13 | - | Fundamentals (financial statements & ratios) |
| 351 | Adj. D&A Margin, % | Yes | Q | - | 15 | - | Fundamentals (financial statements & ratios) |
| 352 | Current Ratio | Yes | Q | - | 41 | - | Fundamentals (financial statements & ratios) |
| 353 | Quick Ratio | Yes | Q | - | 42 | - | Fundamentals (financial statements & ratios) |
| 354 | Cash Ratio |  | Q | - | 43 | - | Fundamentals (financial statements & ratios) |
| 355 | Loan to Assets Ratio, % | Yes | Q | - | 108 | - | Fundamentals (financial statements & ratios) |
| 356 | Loan to Deposit Ratio, % | Yes | Q | - | 109 | - | Fundamentals (financial statements & ratios) |
| 357 | Accounts Receivable Turnover | Yes | Q | - | 30 | - | Fundamentals (financial statements & ratios) |
| 358 | Accounts Payable Turnover | Yes | Q | - | 34 | - | Fundamentals (financial statements & ratios) |
| 359 | Inventory Turnover | Yes | Q | - | 32 | - | Fundamentals (financial statements & ratios) |
| 360 | Days Sales Outstanding (DSO) | Yes | Q | - | 31 | - | Fundamentals (financial statements & ratios) |
| 361 | Days Inventory Outstanding (DIO) | Yes | Q | - | 33 | - | Fundamentals (financial statements & ratios) |
| 362 | Days Payable Outstanding (DPO) | Yes | Q | - | 35 | - | Fundamentals (financial statements & ratios) |
| 363 | Cash Conversion Cycle (CCC) | Yes | Q | - | 36 | - | Fundamentals (financial statements & ratios) |
| 364 | Reserves to Surplus Ratio, % |  | Q | - | 107 | - | Fundamentals (financial statements & ratios) |
| 365 | LT Debt/Equity | Yes | Q | - | 61 | - | Fundamentals (financial statements & ratios) |
| 366 | LT Debt/Total Capital | Yes | Q | - | 62 | - | Fundamentals (financial statements & ratios) |
| 367 | LT Debt/Total Assets | Yes | Q | - | 63 | - | Fundamentals (financial statements & ratios) |
| 368 | Total Debt/Shareholders' Equity | Yes | Q | - | 59 | - | Fundamentals (financial statements & ratios) |
| 369 | Total Debt/Total Capital | Yes | Q | - | 60 | - | Fundamentals (financial statements & ratios) |
| 370 | Total Debt/Total Assets | Yes | Q | - | 64 | - | Fundamentals (financial statements & ratios) |
| 371 | Total Liabilities/Total Assets | Yes | Q | - | 66 | - | Fundamentals (financial statements & ratios) |
| 372 | Total Assets/Shareholders' Equity | Yes | Q | - | 58 | - | Fundamentals (financial statements & ratios) |
| 373 | EBIT/Interest Expenses |  | Q | - | 46 | - | Fundamentals (financial statements & ratios) |
| 374 | EBITDA/Interest Expenses |  | Q | - | 47 | - | Fundamentals (financial statements & ratios) |
| 375 | (EBITDA-CapEx)/Interest Expenses | Yes | Q | - | 48 | - | Fundamentals (financial statements & ratios) |
| 376 | Total Debt/EBITDA | Yes | Q | - | 49 | - | Fundamentals (financial statements & ratios) |
| 377 | Total Debt/Operating Cash Flow | Yes | Q | - | 51 | - | Fundamentals (financial statements & ratios) |
| 378 | Total Debt/(EBITDA-CapEx) | Yes | Q | - | 52 | - | Fundamentals (financial statements & ratios) |
| 379 | Net Debt/EBITDA | Yes | Q | - | 50 | - | Fundamentals (financial statements & ratios) |
| 380 | Net Debt/(EBITDA-CapEx) | Yes | Q | - | 55 | - | Fundamentals (financial statements & ratios) |
| 381 | Net Debt/Operating Cash Flow | Yes | Q | - | 53 | - | Fundamentals (financial statements & ratios) |
| 382 | Unlevered FCF/Total Debt | Yes | Q | - | 54 | - | Fundamentals (financial statements & ratios) |
| 383 | Capex/PP&E | Yes | Q | - | 70 | - | Fundamentals (financial statements & ratios) |
| 384 | Capex/D&A | Yes | Q | - | 69 | - | Fundamentals (financial statements & ratios) |
| 385 | D&A/PP&E | Yes | Q | - | 71 | - | Fundamentals (financial statements & ratios) |
| 386 | Net Working Capital/Average Assets |  | Q | - | 74 | - | Fundamentals (financial statements & ratios) |
| 387 | Fixed Asset Turnover |  | Q | - | 37 | - | Fundamentals (financial statements & ratios) |
| 388 | Total Asset Turnover | Yes | Q | - | 38 | - | Fundamentals (financial statements & ratios) |
| 389 | Dividend Payout Ratio, % |  | Q | - | 78 | - | Fundamentals (financial statements & ratios) |
| 390 | LTM Dividend Payout Ratio (%) |  | LTM | - | 79 | - | Fundamentals (financial statements & ratios) |
| 391 | P/E | Yes | D/M | - | 112 | - | Valuation multiples |
| 392 | Adj. P/E | Yes | D/M | - | 113 | - | Valuation multiples |
| 393 | P/Sales | Yes | D/M | - | 114 | - | Valuation multiples |
| 394 | P/Adj. Sales | Yes | D/M | - | 115 | - | Valuation multiples |
| 395 | P/BV | Yes | D/M | - | 116 | - | Valuation multiples |
| 396 | P/TBV | Yes | D/M | - | 117 | - | Valuation multiples |
| 397 | P/CashFlow | Yes | D/M | - | 118 | - | Valuation multiples |
| 398 | P/FCF | Yes | D/M | - | 119 | - | Valuation multiples |
| 399 | P/FFO | Yes | D/M | - | 137 | - | Valuation multiples |
| 400 | EV/Sales | Yes | D/M | - | 121 | - | Valuation multiples |
| 401 | EV/Adj. Sales | Yes | D/M | - | 122 | - | Valuation multiples |
| 402 | EV/Gross Profit | Yes | D/M | - | 123 | - | Valuation multiples |
| 403 | EV/Adj. Gross Profit | Yes | D/M | - | 124 | - | Valuation multiples |
| 404 | EV/EBITDA | Yes | D/M | - | 125 | - | Valuation multiples |
| 405 | EV/Adj. EBITDA | Yes | D/M | - | 126 | - | Valuation multiples |
| 406 | EV/EBIT | Yes | D/M | - | 127 | - | Valuation multiples |
| 407 | EV/Adj. EBIT | Yes | D/M | - | 128 | - | Valuation multiples |
| 408 | EV/FCF | Yes | D/M | - | 129 | - | Valuation multiples |
| 409 | EV/(EBITDA-CapEx) | Yes | D/M | - | 130 | - | Valuation multiples |
| 410 | Adj. EV/(EBITDA-CapEx) | Yes | Q | - | 131 | - | Valuation multiples |
| 411 | FCF Yield (based on Market Cap) | Yes | Q | - | 132 | - | Valuation multiples |
| 412 | Unlevered FCF Yield, % | Yes | Q | - | 133 | - | Valuation multiples |
| 413 | Dividend Yield (%) |  | Q | - | 77 | - | Valuation multiples |
| 414 | PEG | Yes | Q | - | 134 | - | Valuation multiples |
| 415 | Net Debt/EV | Yes | Q | - | 135 | - | Valuation multiples |
| 416 | Total Debt/EV | Yes | Q | - | 136 | - | Valuation multiples |
| 417 | P/AFFO | Yes | Q | - | 120 | - | Valuation multiples |
| 418 | Market Capitalization |  | D/M | - | 138 | - | Market / price & volume |
| 419 | Enterprise Value |  | D/M | - | 139 | - | Market / price & volume |
| 420 | Total Shares Outstanding (EoP Basic) |  | Q | - | 140 | - | Market / price & volume |
| 421 | Shares per Listing |  | Q | - | 141 | - | Market / price & volume |
| 422 | Enterprise Value per Share |  | D/M | - | 142 | - | Market / price & volume |
| 423 | Stock Price (End Of Day) |  | D/M | - | 143 | - | Market / price & volume |
| 424 | Stock Price-Open |  | D/M | - | 144 | - | Market / price & volume |
| 425 | Stock Price-High |  | D/M | - | 145 | - | Market / price & volume |
| 426 | Stock Price-Low |  | D/M | - | 146 | - | Market / price & volume |
| 427 | Share Price |  | D/M | - | - | 17 | Market / price & volume |
| 428 | Last Close Price |  | D/M | - | - | 18 | Market / price & volume |
| 429 | Last Traded Price |  | D/M | - | 147 | - | Market / price & volume |
| 430 | Last Transaction Volume |  | D/M | - | 148 | - | Market / price & volume |
| 431 | Last Trade Date Time |  | D/M | - | 149 | - | Market / price & volume |
| 432 | 52 Week High |  | W | - | - | 22 | Market / price & volume |
| 433 | 52 Week High Date |  | W | - | - | 24 | Market / price & volume |
| 434 | 52 Week High Change, % |  | W | - | - | 23 | Market / price & volume |
| 435 | 52 Week Low |  | W | - | - | 25 | Market / price & volume |
| 436 | 52 Week Low Date |  | W | - | - | 27 | Market / price & volume |
| 437 | 52 Week Low Change, % |  | W | - | - | 26 | Market / price & volume |
| 438 | Daily Volume |  | D/M | - | - | 19 | Market / price & volume |
| 439 | Average Daily Volume |  | D/M | - | - | - | Market / price & volume |
| 440 | Dollar Volume Liquidity |  | D/M | - | - | - | Market / price & volume |
| 441 | 10 Day Dollar Volume Liquidity |  | D/M | - | - | - | Market / price & volume |
| 442 | 20 Day Dollar Volume Liquidity |  | D/M | - | - | - | Market / price & volume |
| 443 | 30 Day Dollar Volume Liquidity |  | D/M | - | - | - | Market / price & volume |
| 444 | 60 Day Dollar Volume Liquidity |  | D/M | - | - | - | Market / price & volume |
| 445 | 90 Day Dollar Volume Liquidity |  | D/M | - | - | - | Market / price & volume |
| 446 | Intraday Cummulative Trade Volume (live) |  | D/M | - | - | - | Market / price & volume |
| 447 | Intraday Stock Price Change (Live), % |  | D/M | - | - | - | Market / price & volume |
| 448 | Stock Price Percent Change |  | D/M | - | - | - | Market / price & volume |
| 449 | Intraday Price Change (live) |  | D/M | - | - | - | Market / price & volume |
| 450 | Stock Price Change (abs) |  | D/M | - | - | - | Market / price & volume |
| 451 | Total Return |  | D/M | - | - | - | Market / price & volume |
| 452 | Total Return Index |  | D/M | - | - | - | Market / price & volume |
| 453 | Stock Price Return |  | D/M | - | - | - | Market / price & volume |
| 454 | Stock Price Return Index |  | D/M | - | - | - | Market / price & volume |
| 455 | VWAP |  | D/M | - | - | - | Market / price & volume |
| 456 | YTD Price |  | LTM | - | - | - | Market / price & volume |
| 457 | YTD Change |  | LTM | - | - | - | Market / price & volume |
| 458 | YTD,% Change |  | LTM | - | - | - | Market / price & volume |
| 459 | Previous Day Close |  | D/M | - | - | - | Market / price & volume |
| 460 | Previous Close Date |  | D/M | - | - | - | Market / price & volume |
| 461 | 10 Day Average Daily Volume |  | D/M | - | - | - | Market / price & volume |
| 462 | 20 Day Average Daily Volume |  | D/M | - | - | - | Market / price & volume |
| 463 | 30 Day Average Daily Volume |  | D/M | - | - | - | Market / price & volume |
| 464 | 60 Day Average Daily Volume |  | D/M | - | - | - | Market / price & volume |
| 465 | 90 Day Average Daily Volume |  | D/M | - | - | - | Market / price & volume |
| 466 | MIC |  | D/M | - | - | - | Market / price & volume |
| 467 | Stock Price change (live) |  | D/M | - | - | - | Market / price & volume |
| 468 | Stock Price Change (Live), % |  | D/M | - | - | - | Market / price & volume |
| 469 | FX Rate |  | D/M | - | - | - | Market / price & volume |
| 470 | Price Target - Mean |  | M | - | - | 39 | Consensus ratings & price targets |
| 471 | Price Target - Median |  | M | - | - | 40 | Consensus ratings & price targets |
| 472 | Price Target - Low |  | M | - | - | 41 | Consensus ratings & price targets |
| 473 | Price Target - High |  | M | - | - | 42 | Consensus ratings & price targets |
| 474 | Price Target - Number of Contributors |  | M | - | - | 43 | Consensus ratings & price targets |
| 475 | Price Target - Standard Deviation |  | M | - | - | 44 | Consensus ratings & price targets |
| 476 | Rating - Number of Strong Buys |  | M | - | - | 30 | Consensus ratings & price targets |
| 477 | Rating - Number of Buys |  | M | - | - | 31 | Consensus ratings & price targets |
| 478 | Rating - Number of Holds |  | M | - | - | 32 | Consensus ratings & price targets |
| 479 | Rating - Number of Sells |  | M | - | - | 33 | Consensus ratings & price targets |
| 480 | Rating - Number of Strong Sells |  | M | - | - | 34 | Consensus ratings & price targets |
| 481 | Rating - Mean Recommendation |  | M | - | - | 35 | Consensus ratings & price targets |
| 482 | Rating - Label |  | M | - | - | 29 | Consensus ratings & price targets |
| 483 | Rating - No Opinion |  | M | - | - | 36 | Consensus ratings & price targets |
| 484 | Rating - Number of Recommendations |  | M | - | - | 37 | Consensus ratings & price targets |
| 485 | Company Name |  | N/A | - | - | 7 | Descriptive / reference (static) |
| 486 | Sector (GICS L1) |  | N/A | - | - | 10 | Descriptive / reference (static) |
| 487 | Industry Group (GICS L2) |  | N/A | - | - | - | Descriptive / reference (static) |
| 488 | Industry (GICS L3) |  | N/A | - | - | - | Descriptive / reference (static) |
| 489 | Sub-sector (GICS L4) |  | N/A | - | - | 11 | Descriptive / reference (static) |
| 490 | Security Type |  | N/A | - | - | - | Descriptive / reference (static) |
| 491 | Country of Incorporation |  | N/A | - | - | - | Descriptive / reference (static) |
| 492 | Country of Headquaters |  | N/A | - | - | 8 | Descriptive / reference (static) |
| 493 | Country of Stock Exchange |  | N/A | - | - | 13 | Descriptive / reference (static) |
| 494 | Quote Name |  | N/A | - | - | - | Descriptive / reference (static) |
| 495 | Security Name |  | N/A | - | - | - | Descriptive / reference (static) |
| 496 | Issuer Name |  | N/A | - | - | - | Descriptive / reference (static) |
| 497 | Stock Exchange |  | N/A | - | - | 14 | Descriptive / reference (static) |
| 498 | Trading Currency |  | N/A | - | - | 9 | Descriptive / reference (static) |
| 499 | Reporting Currency |  | N/A | - | - | 12 | Descriptive / reference (static) |
| 500 | Employee Count |  | N/A | - | - | - | Descriptive / reference (static) |
| 501 | Employees (Latest) |  | N/A | - | - | - | Descriptive / reference (static) |
| 502 | Earnings Date |  | N/A | - | - | - | Descriptive / reference (static) |
| 503 | Financial Period End Date |  | N/A | - | - | 15 | Descriptive / reference (static) |
| 504 | Financial Period |  | N/A | - | - | - | Descriptive / reference (static) |
| 505 | Company Website |  | N/A | - | - | - | Descriptive / reference (static) |
| 506 | City |  | N/A | - | - | - | Descriptive / reference (static) |
| 507 | State/Region |  | N/A | - | - | - | Descriptive / reference (static) |
| 508 | Postcode |  | N/A | - | - | - | Descriptive / reference (static) |
| 509 | Full Business Address |  | N/A | - | - | - | Descriptive / reference (static) |
| 510 | Company Description |  | N/A | - | - | - | Descriptive / reference (static) |
| 511 | IPO Date |  | N/A | - | - | - | Descriptive / reference (static) |
| 512 | IPO Offer Price |  | N/A | - | - | - | Descriptive / reference (static) |
| 513 | Peers & Competitors |  | N/A | - | - | - | Descriptive / reference (static) |
| 514 | Exact Period End Date |  | N/A | - | - | - | Descriptive / reference (static) |

## Sheet `Available Consensus` (177 rows = header + 176 metrics)

Columns: `metric_name` (A), `excel_code` (B, provider mnemonic, unique), `category` (C).

Category distribution: `Balance Sheet`=42, `Income Statement`=32, `Trading Multiples`=27, `Margins`=19, `Cash Flow Statement`=13, `Coverage Ratios`=8, `Leverage Ratios`=8, `Adjusted Margins`=7, `Operating Ratios`=7, `Capital Intensity Ratios`=4, `Liquidity Ratios`=4, `Profitability Ratios`=4, `Dividend Summary`=1 (sum 176 = 176).

| AC row | metric_name | excel_code | category |
|--------|-------------|------------|----------|
| 2 | Adj. Gross Margin, % | `GROSS_MARGIN_ADJ` | Adjusted Margins |
| 3 | Adj. D&A Margin, % | `DA_MARGIN_ADJ` | Adjusted Margins |
| 4 | Adj. EBIT Margin, % | `EBIT_MARGIN_ADJ` | Adjusted Margins |
| 5 | Adj. R&D Margin, % | `RD_MARGIN_ADJ` | Adjusted Margins |
| 6 | Adj. EBITDA Margin, % | `EBITDA_MARGIN_ADJ` | Adjusted Margins |
| 7 | Adj. SG&A Margin, % | `SGA_MARGIN_ADJ` | Adjusted Margins |
| 8 | Adj. Net Income to Common Shareholders Margin, % | `NI_COMMON_MARGIN_ADJ` | Adjusted Margins |
| 9 | Cash and Cash Equivalents and Short Term Investments | `CASH_AND_ST_INVT` | Balance Sheet |
| 10 | Receivables, Net | `REC_NET` | Balance Sheet |
| 11 | Total Inventory, Net | `INV_NET` | Balance Sheet |
| 12 | Total Current Assets | `CURR_ASSET` | Balance Sheet |
| 13 | PP&E, Net | `PPE_NET` | Balance Sheet |
| 14 | Intangible Assets (Incl. Goodwill) | `INTANGIBLE_INCL_GW` | Balance Sheet |
| 15 | Total Non-Current Assets | `NON_CURR_ASSET` | Balance Sheet |
| 16 | Total Assets | `TOT_ASSET` | Balance Sheet |
| 17 | Payables | `PAYABLES` | Balance Sheet |
| 18 | Accounts Payable and Current Accrued Expenses | `PAYABLE_AND_CURR_AE` | Balance Sheet |
| 19 | Current Debt and Lease Obligation | `CURR_DEBT_AND_LEASE` | Balance Sheet |
| 20 | Total Current Liabilities | `CURR_LIAB` | Balance Sheet |
| 21 | Long Term Debt and Lease Obligation | `NON_CURR_DEBT_AND_LEASE` | Balance Sheet |
| 22 | Total Non-Current Liabilities | `NON_CURR_LIAB` | Balance Sheet |
| 23 | Total Liabilities | `TOT_LIAB` | Balance Sheet |
| 24 | Share and Additional Paid-In Capital | `CAPITAL_STOCK_AND_APIC` | Balance Sheet |
| 25 | Retained Earnings | `RETAINED_EARNINGS` | Balance Sheet |
| 26 | Treasury Stock | `TREASURY_STOCK` | Balance Sheet |
| 27 | Total Stockholders Equity | `TOT_SE` | Balance Sheet |
| 28 | Minority Interest | `NCI_BS` | Balance Sheet |
| 29 | Total Stockholders Equity including Minority Interest | `TOT_SE_INCL_NCI` | Balance Sheet |
| 30 | Total Liabilities and Stockholders Equity | `TOT_LIAB_AND_SE` | Balance Sheet |
| 31 | Net Loan | `NET_LOAN` | Balance Sheet |
| 32 | Deferred Tax Assets | `DEFERRED_TAX_ASSETS` | Balance Sheet |
| 33 | Total Deposits | `TOTAL_DEPOSITS` | Balance Sheet |
| 34 | Book Value | `BOOK_VALUE` | Balance Sheet |
| 35 | Gross Loan | `GROSS_LOAN` | Balance Sheet |
| 36 | Allowance for Loans and Lease Losses | `ALLOWANCE_FOR_LOANS_LEASE_LOSSES` | Balance Sheet |
| 37 | Interest Bearing Deposits Liabilities | `INT_BEARING_DEPOSITS_LIABILITIES` | Balance Sheet |
| 38 | Non Interest Bearing Deposits | `NON_INT_BEARING_DEPOSITS` | Balance Sheet |
| 39 | Tangible Book Value | `TANGIBLE_BOOK_VALUE` | Balance Sheet |
| 40 | Tangible Book Value per Share | `TBVPS` | Balance Sheet |
| 41 | Book Value per Share | `BVPS` | Balance Sheet |
| 42 | Total Debt and Lease Obligation | `TOT_DEBT_AND_LEASE` | Balance Sheet |
| 43 | Net Debt | `NET_DEBT` | Balance Sheet |
| 44 | Total Share Count (EoP) | `ORDINARY_SHARES_EOP` | Balance Sheet |
| 45 | Deferred Tax Liabilities | `DEFERRED_TAX_LIABILITIES` | Balance Sheet |
| 46 | Accrued Expenses | `ACCRUED_EXP` | Balance Sheet |
| 47 | Net Interest Margin_2, % | `NET_INT_MARGIN_2` | Balance Sheet |
| 48 | Common Equity Tier 1 Ratio_2, % | `TIER1_COMM_EQUITY_RATIO_2` | Balance Sheet |
| 49 | Tier 1 Capital Ratio_2, % | `TIER1_CAPITAL_RATIO_2` | Balance Sheet |
| 50 | Tier 2 Capital Ratio_2, % | `TIER2_CAPITAL_RATIO_2` | Balance Sheet |
| 51 | Total Asset Turnover | `TOTAL_ASSET_TURNOVER` | Capital Intensity Ratios |
| 52 | D&A/PP&E | `DA_TO_PPE` | Capital Intensity Ratios |
| 53 | Capex/PP&E | `CAPEX_TO_PPE` | Capital Intensity Ratios |
| 54 | Capex/D&A | `CAPEX_TO_DA` | Capital Intensity Ratios |
| 55 | Net Income (Loss) From Continuing Operations (CF) | `NI_CONTINOP_CF` | Cash Flow Statement |
| 56 | Depreciation and Amortization | `DA_CF` | Cash Flow Statement |
| 57 | Stock Based Compensation | `SBC_CF` | Cash Flow Statement |
| 58 | Operating Cash Flow | `OCF` | Cash Flow Statement |
| 59 | Capex | `CAPEX` | Cash Flow Statement |
| 60 | Investing Cash Flow | `ICF` | Cash Flow Statement |
| 61 | Increase/(Decrease) in Debt, Net | `CHG_IN_DEBT_NET` | Cash Flow Statement |
| 62 | Financing Cash Flow | `FFCF` | Cash Flow Statement |
| 63 | Increase/(decrease) in Cash and Cash Equivalents | `CASH_NET_CHG` | Cash Flow Statement |
| 64 | Cash and Cash Equivalents - Beginning Balance | `CASH_BOP` | Cash Flow Statement |
| 65 | Cash and Cash Equivalents - Ending Balance | `CASH_EOP` | Cash Flow Statement |
| 66 | Free Cash Flow | `FCF` | Cash Flow Statement |
| 67 | Free Cash Flow per Share | `FCFPS` | Cash Flow Statement |
| 68 | Unlevered FCF/Total Debt | `UFCF_TO_TOT_DEBT` | Coverage Ratios |
| 69 | Net Debt/Operating Cash Flow | `NET_DEBT_TO_OCF` | Coverage Ratios |
| 70 | (EBITDA-CapEx)/Interest Expenses | `EBITDA_LESS_CAPEX_TO_INT_EXP` | Coverage Ratios |
| 71 | Total Debt/EBITDA | `DEBT_TO_EBITDA` | Coverage Ratios |
| 72 | Net Debt/EBITDA | `NET_DEBT_TO_EBITDA` | Coverage Ratios |
| 73 | Total Debt/(EBITDA-CapEx) | `TOT_DEBT_TO_EBITDA_LESS_CAPEX` | Coverage Ratios |
| 74 | Net Debt/(EBITDA-CapEx) | `NET_DEBT_TO_EBITDA_LESS_CAPEX` | Coverage Ratios |
| 75 | Total Debt/Operating Cash Flow | `TOT_DEBT_TO_OCF` | Coverage Ratios |
| 76 | LTM Dividend Payout Ratio, % | `LTM_DIV_PAYOUT_RATIO` | Dividend Summary |
| 77 | Adj. Selling, General and Administrative Expense | `SGA_EXP_ADJ` | Income Statement |
| 78 | Earnings Per Share - WAD | `EPS_WAD` | Income Statement |
| 79 | Net Premiums Written | `NET_PREMIUMS_WRITTEN` | Income Statement |
| 80 | Net Earned Premiums | `NET_EARNED_PREMIUMS` | Income Statement |
| 81 | Adj. Research and Development Expense | `RD_EXP_ADJ` | Income Statement |
| 82 | Funds From Operations (FFO) | `FFO` | Income Statement |
| 83 | Funds From Operations Per Share | `FFOPS` | Income Statement |
| 84 | Adj. Depreciation and Amortization Expense | `DA_EXP_OP_ADJ` | Income Statement |
| 85 | Net Interest Income | `NET_INT_INC` | Income Statement |
| 86 | Investment Banking Profit | `IB_PROFIT` | Income Statement |
| 87 | Non-Interest Revenue | `NON_INT_REV` | Income Statement |
| 88 | Adj. Interest Income (Expense), Net | `INT_INC_NET_ADJ` | Income Statement |
| 89 | Total Non-Interest Expense | `TOTAL_NON_INT_EXP` | Income Statement |
| 90 | Adj. Tax Expense | `TAX_EXP_ADJ` | Income Statement |
| 91 | Adj. EBIT | `EBIT_ADJ` | Income Statement |
| 92 | EBIT | `EBIT` | Income Statement |
| 93 | Adj. Revenue | `REV_ADJ` | Income Statement |
| 94 | Adjusted Funds From Operations (FFO) | `AFFO` | Income Statement |
| 95 | Adjusted Funds From Operations Per Share | `AFFOPS` | Income Statement |
| 96 | Compensation Expense | `COMPENSATION_EXP` | Income Statement |
| 97 | Occupancy and Equipment Expense | `OCCUPANCY_EQUIPMENT_EXP` | Income Statement |
| 98 | Adj. EBT | `EBT_ADJ` | Income Statement |
| 99 | Revenue | `REV` | Income Statement |
| 100 | Effective Tax Rate_2 | `TAX_RATE_2` | Income Statement |
| 101 | Adj. Gross Profit | `GP_ADJ` | Income Statement |
| 102 | Adj. Net Income to Common Shareholders | `NI_BASIC_ADJ` | Income Statement |
| 103 | Net Income to Common Shareholders | `NI_BASIC` | Income Statement |
| 104 | Adj. Cost of Goods Sold | `COGS_ADJ` | Income Statement |
| 105 | Adj. Earnings Per Share - WAD | `EPS_WAD_ADJ` | Income Statement |
| 106 | Dividends Per Share | `DPS` | Income Statement |
| 107 | Adj. EBITDA | `EBITDA_ADJ` | Income Statement |
| 108 | EBITDA | `EBITDA` | Income Statement |
| 109 | Total Liabilities/Total Assets | `TOT_LIAB_TO_ASSET` | Leverage Ratios |
| 110 | Total Debt/Total Assets | `TOT_DEBT_TO_ASSET` | Leverage Ratios |
| 111 | LT Debt/Total Assets | `LT_DEBT_TO_ASSET` | Leverage Ratios |
| 112 | LT Debt/Total Capital | `LT_DEBT_TO_CAPITAL` | Leverage Ratios |
| 113 | LT Debt/Equity | `LT_DEBT_TO_EQUITY` | Leverage Ratios |
| 114 | Total Assets/Shareholders' Equity | `TOT_ASSET_TO_EQUITY` | Leverage Ratios |
| 115 | Total Debt/Shareholders' Equity | `TOT_DEBT_TO_EQUITY` | Leverage Ratios |
| 116 | Total Debt/Total Capital | `TOT_DEBT_TO_CAPITAL` | Leverage Ratios |
| 117 | Loan to Deposit Ratio, % | `LOAN_TO_DEPOSIT_RATIO` | Liquidity Ratios |
| 118 | Loan to Assets Ratio, % | `LOAN_TO_ASSETS_RATIO` | Liquidity Ratios |
| 119 | Current Ratio | `CURRENT_RATIO` | Liquidity Ratios |
| 120 | Quick Ratio | `QUICK_RATIO` | Liquidity Ratios |
| 121 | Unlevered FCF Margin, % | `UFCF_MARGIN` | Margins |
| 122 | Provision for Credit Losses Margin, % | `CREDIT_LOSSES_PROV_MARGIN` | Margins |
| 123 | SG&A Margin, % | `SGA_MARGIN` | Margins |
| 124 | R&D Margin, % | `RD_MARGIN` | Margins |
| 125 | Net Income to Common Shareholders Margin, % | `NI_COMMON_MARGIN` | Margins |
| 126 | Capex Margin, % | `CAPEX_MARGIN` | Margins |
| 127 | Net Interest Margin, % | `NET_INT_MARGIN` | Margins |
| 128 | Effective Tax Rate | `TAX_RATE` | Margins |
| 129 | EBITDA Margin, % | `EBITDA_MARGIN` | Margins |
| 130 | EBIT Margin, % | `EBIT_MARGIN` | Margins |
| 131 | FCF/Net Income to Common Shareholders Margin, % | `FCF_NI_MARGIN` | Margins |
| 132 | Efficiency Ratio, % | `EFFICIENCY_RATIO` | Margins |
| 133 | Cost to Income Ratio, % | `COST_TO_INC_RATIO` | Margins |
| 134 | Common Equity Tier 1 Ratio, % | `TIER1_COMM_EQUITY_RATIO` | Margins |
| 135 | Tier 1 Capital Ratio, % | `TIER1_CAPITAL_RATIO` | Margins |
| 136 | Tier 2 Capital Ratio, % | `TIER2_CAPITAL_RATIO` | Margins |
| 137 | Levered FCF Margin, % | `FCF_MARGIN` | Margins |
| 138 | D&A Margin, % | `DA_MARGIN` | Margins |
| 139 | Gross Margin, % | `GROSS_MARGIN` | Margins |
| 140 | Cash Conversion Cycle (CCC) | `CCC` | Operating Ratios |
| 141 | Days Payable Outstanding (DPO) | `DPO` | Operating Ratios |
| 142 | Accounts Payable Turnover | `PAYABLE_TURNOVER` | Operating Ratios |
| 143 | Days Inventory Outstanding (DIO) | `DIO` | Operating Ratios |
| 144 | Inventory Turnover | `INVENTORY_TURNOVER` | Operating Ratios |
| 145 | Days Sales Outstanding (DSO) | `DSO` | Operating Ratios |
| 146 | Accounts Receivable Turnover | `RECEIVABLE_TURNOVER` | Operating Ratios |
| 147 | Return on Capital Employed | `ROCE` | Profitability Ratios |
| 148 | Return on Assets | `ROA` | Profitability Ratios |
| 149 | Return on Invested Capital | `ROIC` | Profitability Ratios |
| 150 | Return on Equity | `ROE` | Profitability Ratios |
| 151 | P/E | `PE` | Trading Multiples |
| 152 | EV/Adj. Gross Profit | `EV_TO_GP_ADJ` | Trading Multiples |
| 153 | P/BV | `P_TO_BV` | Trading Multiples |
| 154 | P/TBV | `P_TO_TBV` | Trading Multiples |
| 155 | P/CashFlow | `P_TO_CF` | Trading Multiples |
| 156 | P/FCF | `P_TO_FCF` | Trading Multiples |
| 157 | EV/Sales | `EV_TO_SALES` | Trading Multiples |
| 158 | P/Sales | `P_TO_SALES` | Trading Multiples |
| 159 | EV/EBITDA | `EV_TO_EBITDA` | Trading Multiples |
| 160 | EV/EBIT | `EV_TO_EBIT` | Trading Multiples |
| 161 | EV/FCF | `EV_TO_FCF` | Trading Multiples |
| 162 | EV/(EBITDA-CapEx) | `EV_TO_EBITDA_LESS_CAPEX` | Trading Multiples |
| 163 | FCF Yield (based on Market Cap) | `FCF_YIELD_MCAP` | Trading Multiples |
| 164 | Unlevered FCF Yield, % | `UFCF_YIELD_EV` | Trading Multiples |
| 165 | Dividend Yield, % | `DIV_YIELD` | Trading Multiples |
| 166 | P/FFO | `P_TO_FFO` | Trading Multiples |
| 167 | P/AFFO | `P_TO_AFFO` | Trading Multiples |
| 168 | PEG | `PEG` | Trading Multiples |
| 169 | Adj. P/E | `PE_ADJ` | Trading Multiples |
| 170 | P/Adj. Sales | `P_TO_SALES_ADJ` | Trading Multiples |
| 171 | EV/Adj. Sales | `EV_TO_SALES_ADJ` | Trading Multiples |
| 172 | Total Debt/EV | `TOT_DEBT_TO_EV` | Trading Multiples |
| 173 | EV/Adj. EBITDA | `EV_TO_EBITDA_ADJ` | Trading Multiples |
| 174 | EV/Adj. EBIT | `EV_TO_EBIT_ADJ` | Trading Multiples |
| 175 | Adj. EV/(EBITDA-CapEx) | `EV_TO_EBITDA_ADJ_LESS_CAPEX` | Trading Multiples |
| 176 | Net Debt/EV | `NET_DEBT_TO_EV` | Trading Multiples |
| 177 | EV/Gross Profit | `EV_TO_GP` | Trading Multiples |

## M&A field list (col G, rows 2-259 — 258 fields)

A flat list of deal-level fields (not per-security time series). Role suffixes observed: `(Target)`, `(Buyer)`, `(Seller)`, `(Parent Of Target)` etc.; value fields carry explicit `(Usd, Mn)` units.

| W1 row | M&A field |
|--------|-----------|
| 2 | Announcement Date |
| 3 | Close Date |
| 4 | Deal Status |
| 5 | Name(Buyer) |
| 6 | Name(Target) |
| 7 | Industry(Target) |
| 8 | Country(Target) |
| 9 | Adjusted Deal Value (Usd, Mn) |
| 10 | Deal Summary |
| 11 | Deal Attitude |
| 12 | Cancellation Date |
| 13 | Deal Types |
| 14 | Primary Deal Type |
| 15 | Expected Close Date |
| 16 | Deal Purpose |
| 17 | Rumour Date |
| 18 | Value Of The Base Equity (Usd, Mn) |
| 19 | Cash Portion Of Deal Financing (Usd) (Usd, Mn) |
| 20 | Cash And Cash Eq. (Pit) (Target) (Usd, Mn) |
| 21 | Price / Share (Pps) (Cash Only) |
| 22 | # Common Shares Acquired (Th) |
| 23 | # Common Shares Sought (Th) |
| 24 | # Shares Issued To Target (Th) |
| 25 | Contingent Payment As Part Of The Deal Financing (Usd) (Usd, Mn) |
| 26 | Expected Contingent Payment Payout Date |
| 27 | Convertible Debt Portion Of Deal Financing (Usd) (Usd, Mn) |
| 28 | Convertible Preferred Shares Portion Of Deal Financing (Usd) (Usd, Mn) |
| 29 | Debt Portion Of Deal Financing (Usd) (Usd, Mn) |
| 30 | Ev (Pit) (Target) (Usd, Mn) |
| 31 | Future Payout As Part Of The Deal Financing (Usd) (Usd, Mn) |
| 32 | Interest Bearing Debt (Pit) (Target) (Usd, Mn) |
| 33 | Liabilities Assumed As Part Of The Deal Financing (Usd) (Usd, Mn) |
| 34 | Deal Financing Type |
| 35 | Other Means Of Payment As Part Of The Deal Financing (Usd) (Usd, Mn) |
| 36 | Share Of The Company'S Equity Pre-Owned (%) |
| 37 | Share Of The Company'S Equity Sought (%) |
| 38 | Preferred Shares Portion Of Deal Financing (Usd) (Usd, Mn) |
| 39 | Price / Share (Pps) |
| 40 | Source Of Funds |
| 41 | Stock Portion Of Deal Financing (Usd) (Usd, Mn) |
| 42 | Transaction Size (Usd, Mn) |
| 43 | Warrants And Options Portion Of Deal Financing (Usd) (Usd, Mn) |
| 44 | Break-Up Fee To Be Paid By(Target) (Usd, Mn) |
| 45 | Break-Up Fee To Be Paid By(Buyer) (Usd, Mn) |
| 46 | Break-Up Fee To Be Paid By(Parent Of Target) (Usd, Mn) |
| 47 | Break-Up Fee To Be Paid By(Parent Of Buyer) (Usd, Mn) |
| 48 | Break-Up Fee To Be Paid By(Buyer - Pe) (Usd, Mn) |
| 49 | Break-Up Fee To Be Paid By(Seller - Pe) (Usd, Mn) |
| 50 | Additional Commitments(Target) |
| 51 | Additional Commitments(Buyer) |
| 52 | Net Tangible Book Value Of Equity (Pit)(Target) (Usd, Mn) |
| 53 | Net Tangible Book Value Of Equity (Pit)(Buyer) (Usd, Mn) |
| 54 | Net Tangible Book Value Of Equity (Pit)(Parent Of Target) (Usd, Mn) |
| 55 | Net Tangible Book Value Of Equity (Pit)(Parent Of Buyer) (Usd, Mn) |
| 56 | Total Cash & Eq. (Pit)(Target) (Usd, Mn) |
| 57 | Total Cash & Eq. (Pit)(Buyer) (Usd, Mn) |
| 58 | Total Cash & Eq. (Pit)(Parent Of Target) (Usd, Mn) |
| 59 | Total Cash & Eq. (Pit)(Parent Of Buyer) (Usd, Mn) |
| 60 | Net Tangible Book Value Per Share Of Equity (Pit)(Target) |
| 61 | Net Tangible Book Value Per Share Of Equity (Pit)(Buyer) |
| 62 | Net Tangible Book Value Per Share Of Equity (Pit)(Parent Of Target) |
| 63 | Net Tangible Book Value Per Share Of Equity (Pit)(Parent Of Buyer) |
| 64 | Current Portion Of Cap. Lease. Obligations (Pit)(Target) (Usd, Mn) |
| 65 | Current Portion Of Cap. Lease. Obligations (Pit)(Buyer) (Usd, Mn) |
| 66 | Current Portion Of Cap. Lease. Obligations (Pit)(Parent Of Target) (Usd, Mn) |
| 67 | Current Portion Of Cap. Lease. Obligations (Pit)(Parent Of Buyer) (Usd, Mn) |
| 68 | Current Portion Of Lt Debt (Pit)(Target) (Usd, Mn) |
| 69 | Current Portion Of Lt Debt (Pit)(Buyer) (Usd, Mn) |
| 70 | Current Portion Of Lt Debt (Pit)(Parent Of Target) (Usd, Mn) |
| 71 | Current Portion Of Lt Debt (Pit)(Parent Of Buyer) (Usd, Mn) |
| 72 | D&A Exp. (Ltm) (Pit)(Target) (Usd, Mn) |
| 73 | D&A Exp. (Ltm) (Pit)(Buyer) (Usd, Mn) |
| 74 | D&A Exp. (Ltm) (Pit)(Parent Of Target) (Usd, Mn) |
| 75 | D&A Exp. (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) |
| 76 | Ebitda (Ltm) (Pit)(Target) (Usd, Mn) |
| 77 | Ebitda (Ltm) (Pit)(Buyer) (Usd, Mn) |
| 78 | Ebitda (Ltm) (Pit)(Parent Of Target) (Usd, Mn) |
| 79 | Ebitda (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) |
| 80 | Ebit (Ltm) (Pit)(Target) (Usd, Mn) |
| 81 | Ebit (Ltm) (Pit)(Buyer) (Usd, Mn) |
| 82 | Ebit (Ltm) (Pit)(Parent Of Target) (Usd, Mn) |
| 83 | Ebit (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) |
| 84 | Eps (Ltm) (Pit)(Target) |
| 85 | Eps (Ltm) (Pit)(Buyer) |
| 86 | Eps (Ltm) (Pit)(Parent Of Target) |
| 87 | Eps (Ltm) (Pit)(Parent Of Buyer) |
| 88 | Total Diluted Shares Outstanding (Pit)(Target) (Th) |
| 89 | Total Diluted Shares Outstanding (Pit)(Buyer) (Th) |
| 90 | Total Diluted Shares Outstanding (Pit)(Parent Of Target) (Th) |
| 91 | Total Diluted Shares Outstanding (Pit)(Parent Of Buyer) (Th) |
| 92 | Interest Exp. (Ltm) (Pit)(Target) (Usd, Mn) |
| 93 | Interest Exp. (Ltm) (Pit)(Buyer) (Usd, Mn) |
| 94 | Interest Exp. (Ltm) (Pit)(Parent Of Target) (Usd, Mn) |
| 95 | Interest Exp. (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) |
| 96 | Lt Debt  (Pit)(Target) (Usd, Mn) |
| 97 | Lt Debt  (Pit)(Buyer) (Usd, Mn) |
| 98 | Lt Debt  (Pit)(Parent Of Target) (Usd, Mn) |
| 99 | Lt Debt  (Pit)(Parent Of Buyer) (Usd, Mn) |
| 100 | Notes Payables (Pit)(Target) (Usd, Mn) |
| 101 | Notes Payables (Pit)(Buyer) (Usd, Mn) |
| 102 | Notes Payables (Pit)(Parent Of Target) (Usd, Mn) |
| 103 | Notes Payables (Pit)(Parent Of Buyer) (Usd, Mn) |
| 104 | Other Short Term Debt (Pit)(Target) (Usd, Mn) |
| 105 | Other Short Term Debt (Pit)(Buyer) (Usd, Mn) |
| 106 | Other Short Term Debt (Pit)(Parent Of Target) (Usd, Mn) |
| 107 | Other Short Term Debt (Pit)(Parent Of Buyer) (Usd, Mn) |
| 108 | Profit Before Tax (Ltm) (Pit)(Target) (Usd, Mn) |
| 109 | Profit Before Tax (Ltm) (Pit)(Buyer) (Usd, Mn) |
| 110 | Profit Before Tax (Ltm) (Pit)(Parent Of Target) (Usd, Mn) |
| 111 | Profit Before Tax (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) |
| 112 | Revenue (Ltm) (Pit)(Target) (Usd, Mn) |
| 113 | Revenue (Ltm) (Pit)(Buyer) (Usd, Mn) |
| 114 | Revenue (Ltm) (Pit)(Parent Of Target) (Usd, Mn) |
| 115 | Revenue (Ltm) (Pit)(Parent Of Buyer) (Usd, Mn) |
| 116 | Total Shares Outstanding (Pit)(Target) (Th) |
| 117 | Total Shares Outstanding (Pit)(Buyer) (Th) |
| 118 | Total Shares Outstanding (Pit)(Parent Of Target) (Th) |
| 119 | Total Shares Outstanding (Pit)(Parent Of Buyer) (Th) |
| 120 | Total Assets (Pit)(Target) (Usd, Mn) |
| 121 | Total Assets (Pit)(Buyer) (Usd, Mn) |
| 122 | Total Assets (Pit)(Parent Of Target) (Usd, Mn) |
| 123 | Total Assets (Pit)(Parent Of Buyer) (Usd, Mn) |
| 124 | Total Deposits (Pit)(Target) (Usd, Mn) |
| 125 | Total Deposits (Pit)(Buyer) (Usd, Mn) |
| 126 | Total Deposits (Pit)(Parent Of Target) (Usd, Mn) |
| 127 | Total Deposits (Pit)(Parent Of Buyer) (Usd, Mn) |
| 128 | City, State, And Post Code(Target) |
| 129 | City, State, And Post Code(Buyer) |
| 130 | City, State, And Post Code(Parent Of Target) |
| 131 | City, State, And Post Code(Parent Of Buyer) |
| 132 | City, State, And Post Code(Buyer - Pe) |
| 133 | City, State, And Post Code(Seller - Pe) |
| 134 | Country(Buyer) |
| 135 | Country(Parent Of Target) |
| 136 | Country(Parent Of Buyer) |
| 137 | Country(Buyer - Pe) |
| 138 | Country(Seller - Pe) |
| 139 | Name(Parent Of Target) |
| 140 | Name(Parent Of Buyer) |
| 141 | Name(Buyer - Pe) |
| 142 | Name(Seller - Pe) |
| 143 | Fax Number (Target) |
| 144 | Fax Number (Buyer) |
| 145 | Fax Number (Parent Of Target) |
| 146 | Fax Number (Parent Of Buyer) |
| 147 | Fax Number (Buyer - Pe) |
| 148 | Fax Number (Seller - Pe) |
| 149 | Latest 10K Date (Pit)(Target) |
| 150 | Latest 10K Date (Pit)(Buyer) |
| 151 | Latest 10K Date (Pit)(Parent Of Target) |
| 152 | Latest 10K Date (Pit)(Parent Of Buyer) |
| 153 | Street Address (Line 1) (Target) |
| 154 | Street Address (Line 1) (Buyer) |
| 155 | Street Address (Line 1) (Parent Of Target) |
| 156 | Street Address (Line 1) (Parent Of Buyer) |
| 157 | Street Address (Line 1) (Buyer - Pe) |
| 158 | Street Address (Line 1) (Seller - Pe) |
| 159 | Street Address (Line 2) (Target) |
| 160 | Street Address (Line 2) (Buyer) |
| 161 | Street Address (Line 2) (Parent Of Target) |
| 162 | Street Address (Line 2) (Parent Of Buyer) |
| 163 | Street Address (Line 2) (Buyer - Pe) |
| 164 | Street Address (Line 2) (Seller - Pe) |
| 165 | Street Address (Line 3) (Target) |
| 166 | Street Address (Line 3) (Buyer) |
| 167 | Street Address (Line 3) (Parent Of Target) |
| 168 | Street Address (Line 3) (Parent Of Buyer) |
| 169 | Street Address (Line 3) (Buyer - Pe) |
| 170 | Street Address (Line 3) (Seller - Pe) |
| 171 | Phone Number (Target) |
| 172 | Phone Number (Buyer) |
| 173 | Phone Number (Parent Of Target) |
| 174 | Phone Number (Parent Of Buyer) |
| 175 | Phone Number (Buyer - Pe) |
| 176 | Phone Number (Seller - Pe) |
| 177 | Industry(Buyer) |
| 178 | Industry(Parent Of Target) |
| 179 | Industry(Parent Of Buyer) |
| 180 | Industry(Buyer - Pe) |
| 181 | Industry(Seller - Pe) |
| 182 | Sector(Target) |
| 183 | Sector(Buyer) |
| 184 | Sector(Parent Of Target) |
| 185 | Sector(Parent Of Buyer) |
| 186 | Sector(Buyer - Pe) |
| 187 | Sector(Seller - Pe) |
| 188 | Entity Description(Target) |
| 189 | Entity Description(Buyer) |
| 190 | Entity Description(Parent Of Target) |
| 191 | Entity Description(Parent Of Buyer) |
| 192 | % Deal Premium Vs 5D Prior Price |
| 193 | % Deal Premium Vs 90D Prior Price |
| 194 | % Deal Premium Vs 1D Prior Price |
| 195 | % Deal Premium Vs 1Mth Prior Price |
| 196 | % Deal Premium Vs 30D Prior Price |
| 197 | % Deal Premium Vs 2Mths Prior Price |
| 198 | % Deal Premium Vs 3Wks Prior Price |
| 199 | % Deal Premium Vs 1Y Prior High Price |
| 200 | % Deal Premium Vs 1Y Prior Low Price |
| 201 | % Deal Premium Vs Unaffected Price |
| 202 | Deal Ev / Book Value (X) |
| 203 | Deal Ev / Net Income (X) |
| 204 | Deal Ev/ Ebit (X) |
| 205 | Deal Ev/ Ebitda (X) |
| 206 | Deal Ev / Debt (X) |
| 207 | Deal Ev / Revenue (X) |
| 208 | Deal Price / Eps (X) |
| 209 | Deal Price / Book Value (X) |
| 210 | Deal Price / Ebit (X) |
| 211 | Deal Price / Ebitda (X) |
| 212 | Deal Price / Revenue (X) |
| 213 | (Deal Price + Assumed Debt ) / Book Value (X) |
| 214 | (Deal Price + Assumed Debt ) / Net Income (X) |
| 215 | (Deal Price + Assumed Debt ) / Ebit (X) |
| 216 | (Deal Price + Assumed Debt ) / Ebitda (X) |
| 217 | (Deal Price + Assumed Debt ) / Revenue (X) |
| 218 | Share Price (5Td Pre-Deal)(Target) |
| 219 | Share Price (5Td Pre-Deal)(Buyer) |
| 220 | Share Price (5Td Pre-Deal)(Parent Of Target) |
| 221 | Share Price (5Td Pre-Deal)(Parent Of Buyer) |
| 222 | Share Price (3Mths Pre-Deal)(Target) |
| 223 | Share Price (3Mths Pre-Deal)(Buyer) |
| 224 | Share Price (3Mths Pre-Deal)(Parent Of Target) |
| 225 | Share Price (3Mths Pre-Deal)(Parent Of Buyer) |
| 226 | Share Price (1Td Pre-Deal)(Target) |
| 227 | Share Price (1Td Pre-Deal)(Buyer) |
| 228 | Share Price (1Td Pre-Deal)(Parent Of Target) |
| 229 | Share Price (1Td Pre-Deal)(Parent Of Buyer) |
| 230 | Share Price (1Mth Pre-Deal)(Target) |
| 231 | Share Price (1Mth Pre-Deal)(Buyer) |
| 232 | Share Price (1Mth Pre-Deal)(Parent Of Target) |
| 233 | Share Price (1Mth Pre-Deal)(Parent Of Buyer) |
| 234 | Share Price (12Mth High Pre-Deal)(Target) |
| 235 | Share Price (12Mth High Pre-Deal)(Buyer) |
| 236 | Share Price (12Mth High Pre-Deal)(Parent Of Target) |
| 237 | Share Price (12Mth High Pre-Deal)(Parent Of Buyer) |
| 238 | Share Price (12Mth Low Pre-Deal)(Target) |
| 239 | Share Price (12Mth Low Pre-Deal)(Buyer) |
| 240 | Share Price (12Mth Low Pre-Deal)(Parent Of Target) |
| 241 | Share Price (12Mth Low Pre-Deal)(Parent Of Buyer) |
| 242 | Share Price (30D Pre-Deal)(Target) |
| 243 | Share Price (30D Pre-Deal)(Buyer) |
| 244 | Share Price (30D Pre-Deal)(Parent Of Target) |
| 245 | Share Price (30D Pre-Deal)(Parent Of Buyer) |
| 246 | Share Price (2Mths Pre-Deal)(Target) |
| 247 | Share Price (2Mths Pre-Deal)(Buyer) |
| 248 | Share Price (2Mths Pre-Deal)(Parent Of Target) |
| 249 | Share Price (2Mths Pre-Deal)(Parent Of Buyer) |
| 250 | Share Price (2Wks Pre-Deal)(Target) |
| 251 | Share Price (2Wks Pre-Deal)(Buyer) |
| 252 | Share Price (2Wks Pre-Deal)(Parent Of Target) |
| 253 | Share Price (2Wks Pre-Deal)(Parent Of Buyer) |
| 254 | Share Price - Unaffected Pre-Deal Date(Target) |
| 255 | Share Price - Unaffected Pre-Deal Date(Buyer) |
| 256 | Share Price - Unaffected Pre-Deal Date(Parent Of Target) |
| 257 | Share Price - Unaffected Pre-Deal(Target) |
| 258 | Share Price - Unaffected Pre-Deal(Buyer) |
| 259 | Share Price - Unaffected Pre-Deal(Parent Of Target) |

## Funding field list (col I, rows 2-36 — 35 fields)

| W1 row | Funding field |
|--------|---------------|
| 2 | Announcement Date |
| 3 | Company Name |
| 4 | Funding Type |
| 5 | Amount Raised (Th) |
| 6 | Post-Money Valuation (Usd, Mn) |
| 7 | Industry |
| 8 | Country |
| 9 | Company Description |
| 10 | Funding Stage |
| 11 | Revenue Range (Usd) |
| 12 | Total Funding Amount, Funded Company (Usd, Mn) |
| 13 | All Investor Names, Funded Company |
| 14 | Crunchbase Categories |
| 15 | City |
| 16 | Company Type |
| 17 | Exit Date |
| 18 | Founded Date |
| 19 | Headquarter Location |
| 20 | Latest Funding Amount (Th) |
| 21 | Last Funding Round Date |
| 22 | Last Funding Type |
| 23 | Lead Investor Names, Funded Company |
| 24 | No. Of Employees |
| 25 | No. Of Funding Rounds |
| 26 | Operating Status |
| 27 | No. Of Investors, Funded Company |
| 28 | Closed Date |
| 29 | All Investor Names, Funding Round |
| 30 | Lead Investor Name, Funding Round |
| 31 | No. Of Lead Investors, Funding Round |
| 32 | No. Of Investors, Funding Round |
| 33 | Investment Stage |
| 34 | Pre-Money Valuation (Usd, Mn) |
| 35 | Funding Round Description |
| 36 | Target Money Raised (Th) |

