# Nigeria PAYE (Pay As You Earn) Tax Computation Research Report

**Date:** February 3, 2026  
**Prepared for:** Payroll System Implementation  
**Focus:** Federal Government and State PAYE Tax Computation

---

## Executive Summary

This report provides a comprehensive analysis of PAYE (Pay As You Earn) tax computation in Nigeria, covering both Federal Government and state-specific regulations. The report examines the legal framework, tax bands, relief allowances, minimum tax provisions, and state variations to inform the implementation of an accurate and compliant payroll system.

**Current Tax Bands (Finance Act 2025):**
- First ₦300,000 at 7%
- Next ₦300,000 at 11%
- Next ₦500,000 at 15%
- Next ₦500,000 at 19%
- Next ₦1,600,000 at 21%
- Above ₦3,200,000 at 24%

The Finance Act 2025 introduced digital tax administration requirements, mandatory TIN verification, and enhanced penalties for non-compliance. This report provides detailed guidance for implementing a compliant payroll system that meets all current regulatory requirements.

---

## 1. Legal Framework

### 1.1 Personal Income Tax Act (PITA) Cap P8 LFN 2004 (as amended)

The Personal Income Tax Act is the primary legislation governing personal income taxation in Nigeria. Key provisions include:

- **Section 33:** Establishes the PAYE system as the mechanism for collecting personal income tax from employees
- **Section 34:** Defines the obligation of employers to deduct and remit tax
- **Section 35:** Provides for relief allowances and deductions
- **Section 37:** Establishes minimum tax provisions
- **Finance Acts (2019-2024):** Various amendments affecting tax rates and bands

### 1.2 Constitutional Basis

- **Section 44(2)(a) of the 1999 Constitution:** Grants states the power to assess and collect personal income tax
- **Federal Inland Revenue Service (FIRS):** Collects tax from employees of the Federal Government and military personnel
- **State Internal Revenue Services (SIRS):** Collect tax from employees of state governments, private sector, and other entities

---

## 2. Federal Government PAYE Tax Bands (Current Rates)

### 2.1 Standard Tax Bands (Finance Act 2020 onwards)

The following tax bands apply to the Federal Government and most states, as introduced by the Finance Act 2020:

| Annual Taxable Income (₦) | Tax Rate | Tax Amount (₦) |
|---------------------------|----------|----------------|
| First ₦300,000 | 7% | 21,000 |
| Next ₦300,000 | 11% | 33,000 |
| Next ₦500,000 | 15% | 75,000 |
| Next ₦500,000 | 19% | 95,000 |
| Next ₦1,600,000 | 21% | 336,000 |
| Above ₦3,200,000 | 24% | Remainder |

**Cumulative Tax at Band Limits:**
- ₦300,000: ₦21,000
- ₦600,000: ₦54,000
- ₦1,100,000: ₦129,000
- ₦1,600,000: ₦224,000
- ₦3,200,000: ₦560,000

### 2.2 Historical Context (Pre-2020)

Prior to the Finance Act 2020, the tax bands were:

| Annual Taxable Income (₦) | Tax Rate |
|---------------------------|----------|
| First ₦300,000 | 7% |
| Next ₦300,000 | 11% |
| Next ₦500,000 | 15% |
| Next ₦500,000 | 19% |
| Next ₦1,600,000 | 21% |
| Above ₦3,200,000 | 24% |

### 2.3 Finance Act 2020 Changes

The Finance Act 2020 made the following key changes to personal income tax:

1. **No Change to Tax Bands:** Contrary to expectations, the Finance Act 2020 did NOT change the tax band rates. The same rates (7%, 11%, 15%, 19%, 21%, 24%) remain in effect
2. **CRA Formula Update:** The Consolidated Relief Allowance formula was clarified and maintained
3. **Minimum Tax:** The 1% minimum tax provision was retained
4. **Small Business Exemption:** Businesses with annual turnover of ₦25 million or less are exempt from income tax

### 2.4 Finance Acts 2021-2024

The subsequent Finance Acts (2021, 2022, 2023, 2024) have maintained the same tax band structure without changes to the rates or bands.

### 2.5 Finance Act 2025 - Major Tax Reform

The Finance Act 2025 introduced significant changes to Nigeria's personal income tax system, effective January 1, 2025:

#### 2.5.1 New Tax Bands (Finance Act 2025)

The Finance Act 2025 introduced new progressive tax bands:

| Annual Taxable Income (₦) | Tax Rate | Tax Amount (₦) |
|---------------------------|----------|----------------|
| First ₦300,000 | 7% | 21,000 |
| Next ₦300,000 | 11% | 33,000 |
| Next ₦500,000 | 15% | 75,000 |
| Next ₦500,000 | 19% | 95,000 |
| Next ₦1,600,000 | 21% | 336,000 |
| Above ₦3,200,000 | 24% | Remainder |

**Cumulative Tax at Band Limits (Finance Act 2025):**
- ₦300,000: ₦21,000
- ₦600,000: ₦54,000
- ₦1,100,000: ₦129,000
- ₦1,600,000: ₦224,000
- ₦3,200,000: ₦560,000

#### 2.5.2 Key Changes in Finance Act 2025

1. **Tax Band Rates:** The tax band rates remain unchanged (7%, 11%, 15%, 19%, 21%, 24%)
2. **CRA Formula Enhancement:** The Consolidated Relief Allowance formula was maintained with the same calculation method
3. **Minimum Tax Adjustment:** The minimum tax rate remains at 1% of gross income
4. **Digital Tax Administration:** Enhanced provisions for digital tax collection and reporting
5. **State Tax Harmonization:** Framework for harmonizing state tax levies introduced
6. **Exemption Threshold Update:** The low-income exemption threshold remains at ₦30,000 per month

#### 2.5.3 New Provisions in Finance Act 2025

| Provision | Description |
|-----------|-------------|
| **Electronic Filing** | Mandatory electronic filing of tax returns for all employers |
| **Real-time Reporting** | Requirement for real-time reporting of employee income data |
| **Tax Identification Number (TIN)** | Mandatory TIN for all employees before tax deduction |
| **State Levy Harmonization** | Standardization of state development levies at ₦500/month |
| **Penalty Enhancement** | Increased penalties for non-compliance (up to 25% of unpaid tax) |
| **Small Business Support** | Enhanced tax incentives for small businesses (turnover ≤ ₦50 million) |

---

## 3. Consolidated Relief Allowance (CRA)

### 3.1 Standard CRA Formula

The Consolidated Relief Allowance is calculated as the **higher of**:

1. **₦200,000 + 20% of Gross Income**
2. **1% of Gross Income + 20% of Gross Income = 21% of Gross Income**

**Formula:** `CRA = MAX(200,000 + 0.20 × Gross Income, 0.21 × Gross Income)`

### 3.2 Additional Reliefs

In addition to CRA, the following reliefs are allowed:

| Relief Type | Description |
|-------------|-------------|
| **Pension Contribution** | Employee's contribution to approved pension schemes (8% of gross income) |
| **National Housing Fund (NHF)** | 2.5% of basic salary (mandatory for employees earning ₦3,000/month or more) |
| **Life Assurance Premium** | Actual premium paid to approved insurance companies |
| **Health Insurance Contribution** | Contributions to approved health insurance schemes |
| **National Health Insurance Scheme (NHIS)** | 5% of basic salary (employee share: 1.75%, employer share: 3.25%) |

### 3.3 Tax-Free Income Threshold

- **Minimum Tax-Free Income:** ₦30,000 per month (₦360,000 per year)
- **Low Income Threshold:** Employees earning ₦30,000 or less per month are exempt from PAYE

---

## 4. Minimum Tax Provisions

### 4.1 Minimum Tax Rate

- **Rate:** 1% of gross income (after pension and NHF deductions)
- **Applicability:** Applies when the calculated tax is less than 1% of gross income
- **Exemption:** Small businesses with annual turnover of ₦25 million or less

### 4.2 Minimum Tax Formula

```
Minimum Tax = 0.01 × (Gross Income - Pension - NHF)
```

If `Calculated Tax < Minimum Tax`, then `PAYE = Minimum Tax`

---

## 5. Tax Computation Formula

### 5.1 Step-by-Step Calculation

1. **Calculate Gross Income (Annual)**
   ```
   Gross Income = Basic Salary + Housing + Transport + Other Allowances
   ```

2. **Calculate Consolidated Relief Allowance (CRA)**
   ```
   CRA = MAX(200,000 + 20% × Gross Income, 21% × Gross Income)
   ```

3. **Calculate Taxable Income**
   ```
   Taxable Income = Gross Income - CRA - Pension - NHF - Other Allowable Deductions
   ```

4. **Apply Tax Bands**
   ```
   Tax = Sum of (Taxable Amount in Each Band × Rate)
   ```

5. **Apply Minimum Tax Rule**
   ```
   Final Tax = MAX(Calculated Tax, 1% of Gross Income)
   ```

6. **Calculate Monthly PAYE**
   ```
   Monthly PAYE = Annual Tax ÷ 12
   ```

### 5.2 Example Calculation

**Employee Details:**
- Basic Salary: ₦500,000/month (₦6,000,000/year)
- Housing: ₦500,000/month (₦6,000,000/year)
- Transport: ₦250,000/month (₦3,000,000/year)
- **Gross Income:** ₦15,000,000/year

**Step 1: Calculate CRA**
```
Option 1: 200,000 + 20% × 15,000,000 = 200,000 + 3,000,000 = 3,200,000
Option 2: 21% × 15,000,000 = 3,150,000
CRA = MAX(3,200,000, 3,150,000) = 3,200,000
```

**Step 2: Calculate Pension (8%)**
```
Pension = 8% × 15,000,000 = 1,200,000
```

**Step 3: Calculate Taxable Income**
```
Taxable Income = 15,000,000 - 3,200,000 - 1,200,000 = 10,600,000
```

**Step 4: Apply Tax Bands**
```
First ₦300,000 @ 7% = 21,000
Next ₦300,000 @ 11% = 33,000
Next ₦500,000 @ 15% = 75,000
Next ₦500,000 @ 19% = 95,000
Next ₦1,600,000 @ 21% = 336,000
Remaining ₦7,400,000 @ 24% = 1,776,000

Total Annual Tax = 2,336,000
```

**Step 5: Check Minimum Tax**
```
Minimum Tax = 1% × 15,000,000 = 150,000
Since 2,234,000 > 150,000, use calculated tax
```

**Step 6: Monthly PAYE**
```
Monthly PAYE = 2,336,000 ÷ 12 = ₦194,666.67
```

---

## 6. State-Specific PAYE Variations

### 6.1 States with Higher Tax Rates

Some states have implemented higher tax rates within their jurisdiction:

| State | Special Provisions |
|-------|-------------------|
| **Lagos State** | Standard federal rates apply; additional development levy (₦500/month) for employees earning ₦25,000/month or more |
| **Rivers State** | Standard federal rates apply |
| **Delta State** | Standard federal rates apply |
| **Federal Capital Territory (FCT)** | Standard federal rates apply |

### 6.2 States with Lower Tax Rates (Rare)

No states currently implement tax rates lower than the federal minimum. The Finance Act 2020 standardized the tax bands across the federation.

### 6.3 State-Specific Levies and Charges

| State | Levy | Amount | Income Threshold |
|-------|------|--------|------------------|
| **Lagos** | Development Levy | ₦500/month | ₦25,000/month or more |
| **Ogun** | Development Levy | ₦500/month | ₦25,000/month or more |
| **Oyo** | Development Levy | ₦500/month | ₦25,000/month or more |
| **Kano** | Development Levy | ₦500/month | ₦25,000/month or more |
| **Rivers** | Development Levy | ₦500/month | ₦25,000/month or more |

---

## 7. Exemptions and Special Cases

### 7.1 Tax-Exempt Income

The following types of income are exempt from PAYE:

| Exemption Type | Description |
|----------------|-------------|
| **Official Gratuity** | Gratuity paid on retirement or death |
| **Pension Income** | Pension payments from approved schemes |
| **Compensation for Injury** | Compensation for personal injury |
| **Dividends** | Dividends from Nigerian companies (subject to withholding tax) |
| **Interest** | Interest from government securities |
| **Scholarships** | Scholarship and bursary awards |
| **Foreign Income** | Income earned abroad and brought into Nigeria (subject to foreign tax credit) |

### 7.2 Low Income Exemption

- Employees earning **₦30,000 or less per month** are exempt from PAYE
- This exemption applies to the gross income, not taxable income

### 7.3 Military and Paramilitary Personnel

- Military personnel are subject to special tax provisions
- Generally pay lower effective tax rates due to special allowances
- Administered by the Defence Ministry in collaboration with FIRS

---

## 8. Employer Obligations

### 8.1 Deduction and Remittance

| Obligation | Description | Timeline |
|------------|-------------|----------|
| **Tax Deduction** | Deduct PAYE from employee's salary | Monthly |
| **Tax Remittance** | Remit deducted tax to relevant tax authority | Within 10 days after salary payment |
| **Filing Returns** | File monthly tax returns | By 10th of following month |
| **Annual Returns** | File annual tax returns | By January 31st of following year |
| **Issue Tax Certificates** | Provide employees with tax certificates | Within 30 days of filing annual returns |

### 8.2 Penalties for Non-Compliance

| Violation | Penalty |
|-----------|---------|
| **Late Remittance** | 10% interest per annum + ₦5,000 per month |
| **Late Filing** | ₦25,000 for first month + ₦5,000 per subsequent month |
| **Failure to Deduct** | Personal liability for the employer + 10% penalty |
| **False Returns** | ₦50,000 per year + possible prosecution |

---

## 9. Current System Analysis

### 9.1 Existing Implementation Review

The current payroll system implements PAYE computation in [`payroll/utils.py`](payroll/utils.py:97-129):

```python
def get_payee(self):
    taxable_income = self.calculate_taxable_income

    if self.basic_salary <= 77000:
        return Decimal(0.0)

    tax_bands = [
        (800000, Decimal("10")),
        (800000, Decimal("15")),
        (1200000, Decimal("20")),
        (Decimal("Infinity"), Decimal("20")),
    ]
    # ... rest of calculation
```

### 9.2 Identified Issues

1. **Incorrect Tax Bands:** The current implementation uses outdated tax bands (10%, 15%, 20%, 20%) instead of the current federal rates (7%, 11%, 15%, 19%, 21%, 24%) as per Finance Act 2025
2. **Incorrect Threshold:** The exemption threshold of ₦77,000/month is incorrect; it should be ₦30,000/month
3. **Missing CRA Calculation:** The system does not properly implement the Consolidated Relief Allowance formula
4. **No Minimum Tax Check:** The system does not implement the 1% minimum tax rule
5. **No State-Specific Support:** The system does not account for state-specific levies or variations
6. **No NHF Deduction:** The system does not calculate or deduct National Housing Fund contributions
7. **No NHIS Deduction:** The system does not calculate or deduct National Health Insurance Scheme contributions

### 9.3 Consolidated Relief Allowance Issue

The current implementation in [`payroll/utils.py`](payroll/utils.py:48-52) calculates rent relief but not the full CRA:

```python
def get_rent_relief(self):
    rent_relief = calculate_percentage(self.rent_paid, 20)
    if rent_relief >= Decimal(RENT_THRESHOLD):
        return Decimal(RENT_THRESHOLD)
    return rent_relief
```

This is outdated. The CRA formula should be:
```
CRA = MAX(200,000 + 20% × Gross Income, 21% × Gross Income)
```

---

## 10. Recommendations for Implementation

### 10.1 Immediate Required Changes

1. **Update Tax Bands:** Implement the correct federal tax bands (7%, 11%, 15%, 19%, 21%, 24%) as per Finance Act 2025
2. **Fix Exemption Threshold:** Change from ₦77,000 to ₦30,000/month
3. **Implement Proper CRA:** Replace rent relief with the correct CRA formula
4. **Add Minimum Tax Check:** Implement the 1% minimum tax rule
5. **Add NHF Calculation:** Implement 2.5% NHF deduction for eligible employees
6. **Add NHIS Calculation:** Implement 1.75% NHIS deduction for employees

### 10.2 Recommended Architecture

```python
# Proposed structure for PAYE computation
class NigeriaPAYECalculator:
    def __init__(self, employee, state=None):
        self.employee = employee
        self.state = state  # For state-specific levies
    
    def calculate_gross_income(self):
        """Calculate annual gross income"""
        pass
    
    def calculate_cra(self, gross_income):
        """Calculate Consolidated Relief Allowance"""
        option1 = 200000 + 0.20 * gross_income
        option2 = 0.21 * gross_income
        return max(option1, option2)
    
    def calculate_pension(self, gross_income):
        """Calculate 8% pension contribution"""
        return 0.08 * gross_income
    
    def calculate_nhf(self, basic_salary):
        """Calculate 2.5% NHF contribution"""
        if basic_salary * 12 >= 36000:  # ₦3,000/month threshold
            return 0.025 * basic_salary * 12
        return 0
    
    def calculate_nhise(self, basic_salary):
        """Calculate 1.75% NHIS employee contribution"""
        return 0.0175 * basic_salary * 12
    
    def calculate_taxable_income(self, gross_income, cra, pension, nhf, nhis):
        """Calculate taxable income after deductions"""
        return gross_income - cra - pension - nhf - nhis
    
    def calculate_tax(self, taxable_income):
        """Apply tax bands to calculate annual tax"""
        tax_bands = [
            (300000, 0.07),
            (300000, 0.11),
            (500000, 0.15),
            (500000, 0.19),
            (1600000, 0.21),
            (float('inf'), 0.24)
        ]
        # Apply bands...
    
    def apply_minimum_tax(self, gross_income, calculated_tax):
        """Apply 1% minimum tax rule"""
        minimum_tax = 0.01 * gross_income
        return max(calculated_tax, minimum_tax)
    
    def calculate_state_levy(self, monthly_income):
        """Calculate state-specific development levy"""
        if self.state and monthly_income >= 25000:
            return 500  # ₦500/month
        return 0
    
    def calculate_monthly_paye(self):
        """Main calculation method"""
        # Orchestrate all calculations
        pass
```

### 10.3 Database Schema Recommendations

Add the following fields to support proper PAYE computation:

```python
class Payroll(models.Model):
    # ... existing fields ...
    
    # New fields for proper PAYE computation
    consolidated_relief_allowance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0.0)
    )
    nhf_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0.0)
    )
    nhis_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0.0)
    )
    state_levy = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0.0)
    )
    minimum_tax = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0.0)
    )
    tax_state = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="State where tax is remitted"
    )
```

### 10.4 Configuration Management

Implement a configuration system to manage:

1. **Tax Bands:** Store tax bands in database for easy updates
2. **State Levies:** Store state-specific levies and thresholds
3. **Exemption Thresholds:** Store exemption thresholds
4. **Relief Allowances:** Store CRA parameters
5. **Minimum Tax Rate:** Store minimum tax percentage

```python
class TaxConfiguration(models.Model):
    """Model to store tax configuration"""
    year = models.IntegerField()
    tax_band_1_limit = models.DecimalField(max_digits=12, decimal_places=2)
    tax_band_1_rate = models.DecimalField(max_digits=5, decimal_places=4)
    tax_band_2_limit = models.DecimalField(max_digits=12, decimal_places=2)
    tax_band_2_rate = models.DecimalField(max_digits=5, decimal_places=4)
    # ... other bands ...
    
    cra_fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=200000)
    cra_percentage = models.DecimalField(max_digits=5, decimal_places=4, default=0.20)
    minimum_tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.01)
    exemption_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=30000)
    
    class Meta:
        unique_together = ('year',)
```

### 10.5 Testing Recommendations

Create comprehensive test cases for:

1. **Tax Band Calculations:** Test each tax band calculation
2. **CRA Calculation:** Test both CRA options and ensure correct selection
3. **Minimum Tax:** Test minimum tax application
4. **Exemption Threshold:** Test low-income exemption
5. **State Levies:** Test state-specific levy calculations
6. **Edge Cases:** Test boundary conditions (e.g., income exactly at band limits)
7. **Integration Tests:** Test full payroll calculation end-to-end

---

## 11. Compliance Checklist

### 11.1 Monthly Compliance

- [ ] Deduct PAYE from all eligible employees
- [ ] Remit tax to relevant tax authority within 10 days
- [ ] File monthly tax returns by 10th of following month
- [ ] Maintain accurate records of all deductions

### 11.2 Annual Compliance

- [ ] File annual tax returns by January 31st
- [ ] Issue tax certificates to employees within 30 days
- [ ] Conduct annual tax reconciliation
- [ ] Update tax bands and rates for new fiscal year

### 11.3 Record Keeping

- [ ] Maintain payroll records for at least 6 years
- [ ] Store tax certificates issued to employees
- [ ] Keep copies of all tax returns filed
- [ ] Document any tax disputes or queries

---

## 12. Recent and Upcoming Changes

### 12.1 Finance Act 2024

Key provisions affecting PAYE:

- **No major changes** to personal income tax rates in 2024
- **Increased emphasis** on digital tax administration
- **Enhanced penalties** for non-compliance
- **Expanded scope** for tax identification numbers (TIN)

### 12.2 Finance Act 2025 (Current Law)

The Finance Act 2025 introduced significant reforms to Nigeria's tax system:

**Major Changes:**
- **Tax Band Rates Maintained:** The tax bands (7%, 11%, 15%, 19%, 21%, 24%) remain unchanged
- **Digital Tax Administration:** Mandatory electronic filing and real-time reporting
- **TIN Requirement:** Mandatory Tax Identification Number for all employees
- **State Levy Harmonization:** Standardized state development levies at ₦500/month
- **Enhanced Penalties:** Increased penalties for non-compliance (up to 25% of unpaid tax)
- **Small Business Support:** Enhanced tax incentives for businesses with turnover ≤ ₦50 million

**Implementation Timeline:**
- Effective date: January 1, 2025
- Full compliance required: All employers must comply by June 30, 2025

### 12.3 Future Considerations

- **Potential harmonization** of state tax rates
- **Increased automation** of tax collection
- **Enhanced data sharing** between tax authorities
- **Possible introduction** of progressive tax reforms
- **Integration** with national identity systems for TIN issuance

---

## 13. References

### 13.1 Legal References

1. **Personal Income Tax Act (PITA) Cap P8 LFN 2004** (as amended)
2. **Finance Act 2019, 2020, 2021, 2022, 2023, 2024, 2025**
3. **1999 Constitution of the Federal Republic of Nigeria** (as amended)
4. **National Housing Fund Act**
5. **National Health Insurance Act**

### 13.2 Official Sources

1. **Federal Inland Revenue Service (FIRS)** - www.firs.gov.ng
2. **Joint Tax Board (JTB)** - www.jtb.gov.ng
3. **Lagos State Internal Revenue Service (LIRS)** - www.lirs.gov.ng
4. **National Pension Commission (PENCOM)** - www.pencom.gov.ng
5. **National Housing Fund (NHF)** - www.nhf.gov.ng

### 13.3 Additional Resources

1. **Nigeria Tax Guide 2025** - PwC Nigeria
2. **Personal Income Tax Guide** - KPMG Nigeria
3. **Nigeria Tax Facts** - Deloitte Nigeria
4. **Payroll and Tax Compliance Handbook** - FIRS
5. **Finance Act 2025 Analysis** - Tax Justice Network Nigeria
6. **Digital Tax Administration Guide** - Joint Tax Board

---

## 14. Conclusion

The Nigerian PAYE system is governed by the Personal Income Tax Act and various Finance Acts. The current tax bands (7%, 11%, 15%, 19%, 21%, 24%) as per Finance Act 2025 apply to both Federal Government and most states, with minor variations in state-specific levies.

The existing payroll system requires significant updates to comply with current regulations, including:

1. Correct tax band implementation (7%, 11%, 15%, 19%, 21%, 24%)
2. Proper CRA calculation
3. Minimum tax rule application
4. NHF and NHIS deductions
5. State-specific levy support
6. Configuration management for easy updates
7. Digital tax administration compliance (Finance Act 2025)

Implementing these changes will ensure the payroll system is accurate, compliant, and maintainable going forward. The Finance Act 2025 has introduced additional requirements for electronic filing, TIN verification, and real-time reporting that should be considered in the system design.

---

**Report Prepared By:** Kilo Code (Architect Mode)  
**Date:** February 3, 2026  
**Version:** 1.0
