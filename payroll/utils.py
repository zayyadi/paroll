from decimal import Decimal
from num2words import num2words

def get_housing(self):
        return self.basic_salary * 10 / 100

    
def get_transport(self):
    return self.basic_salary *10 / 100


def get_basic(self):
    return self.basic_salary * 40 / 100


def get_bht(self):
    return get_transport(self) + get_housing(self) + get_basic(self)

def get_pension_employee(self):
        if self.basic_salary <= 30000:
            return 0
        return get_bht(self) * 8 / 100
    

def get_pension_employer(self):
    if self.basic_salary <= 30000:
        return 0
    return get_bht(self) * 10 / 100


def get_pension(self):
    if self.basic_salary <= 30000:
        return 0
    return get_pension_employee(self) + get_pension_employer(self)


# def get_gross_income(self):
#     return (self.basic_salary *12) - (get_pension_employee(self)*12)


def get_consolidated_calc(self):
    if (self.get_gross_income * 1/100) > 200000:
        return self.get_gross_income * 1/100
    return 200000


def get_consolidated_relief(self):
    return get_consolidated_calc(self) + (self.get_gross_income * 20/100)


# def calculate_taxable_income(self) -> Decimal:
#     return (
#         (self.get_gross_income)
#         - (get_consolidated_relief(self))
        
#     )


def first_taxable(self) -> Decimal:
    if self.calculate_taxable_income <= 88000:
        return 0


def second_taxable(self) -> Decimal:
    if self.calculate_taxable_income < 300000:
        return (self.calculate_taxable_income) * 7 / 100
    elif self.calculate_taxable_income >= 300000:
        return 300000 * 7 / 100



def third_taxable(self) -> Decimal:
    if (self.calculate_taxable_income - 300000)>0 and (self.calculate_taxable_income - 300000) <= 300000:
        return (self.calculate_taxable_income - 300000) * 11 / 100
    elif (self.calculate_taxable_income - 300000) >= 300000:
        return 300000 * 11 / 100


def fourth_taxable(self) -> Decimal:
    if (self.calculate_taxable_income - 600000) >= 500000:
        return 500000 * 15 / 100

    elif (self.calculate_taxable_income - 600000)> 0 and (self.calculate_taxable_income - 600000) <= 500000:
        return (self.calculate_taxable_income - 600000) * 15 / 100


def fifth_taxable(self) -> Decimal:
    if self.calculate_taxable_income - 1100000 >= 500000:
        return 500000 * 19 / 100
    elif (self.calculate_taxable_income - 1100000)> 0 and (self.calculate_taxable_income - 1100000) <= 500000:
        return (self.calculate_taxable_income - 1100000) * 19 / 100
    

def sixth_taxable(self) -> Decimal:
    if self.calculate_taxable_income - 1600000 >= 1600000:
        return 1600000 * 21 / 100

    elif (self.calculate_taxable_income - 1600000) >0 and (self.calculate_taxable_income - 1600000)< 1600000:
        return (self.calculate_taxable_income - 1600000) * 21 / 100


def seventh_taxable(self) -> Decimal:
    if self.calculate_taxable_income - 3200000 > 3200000:
        return 3200000 * 24 / 100
    

def get_payee(self):
    if self.calculate_taxable_income <= 88000:
            return first_taxable(self)
    elif self.calculate_taxable_income <= 300000:
        return second_taxable(self) / 12
    elif self.calculate_taxable_income >= 300000 and self.calculate_taxable_income < 600000:
        return Decimal(second_taxable(self)) + Decimal(third_taxable(self)) / 12
    elif (
        self.calculate_taxable_income >= 300000
        and self.calculate_taxable_income >= 600000
        and self.calculate_taxable_income < 1100000
    ):
        return (
            Decimal(second_taxable(self))
            + Decimal(third_taxable(self))
            + Decimal(fourth_taxable(self))
        ) / 12
    elif (
        self.calculate_taxable_income >= 1100000
        and self.calculate_taxable_income < 1600000
        ):
        return (
            Decimal(second_taxable(self))
            + Decimal(third_taxable(self))
            + Decimal(fourth_taxable(self))
            + Decimal(fifth_taxable(self))
        ) / 12
    elif (
        self.calculate_taxable_income >= 1600000
        and self.calculate_taxable_income < 3200000
        ):
        return (
            Decimal(second_taxable(self))
            + Decimal(third_taxable(self))
            + Decimal(fourth_taxable(self))
            + Decimal(fifth_taxable(self))
            + Decimal(sixth_taxable(self))
        ) / 12
    elif (
        self.calculate_taxable_income >= 3200000
        ):
        return (
            Decimal(second_taxable(self))
            + Decimal(third_taxable(self))
            + Decimal(fourth_taxable(self))
            + Decimal(fifth_taxable(self))
            + Decimal(sixth_taxable(self))
            + Decimal(seventh_taxable(self))
        )/ 12
        

def get_water_rate(self):
    if self.basic_salary <= 75000:
        return 150
    return 200

def get_net_pay(self):
    return (self.payr.get_gross_income/ 12) - (self.payr.payee/12) - (self.payr.water_rate) \
    + Decimal(self.leave_allowance ) + \
    Decimal(self.overtime) - Decimal(self.lateness) - Decimal(self.absent) - Decimal(self.damage)

# Number Logic

ones = ('Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine')

twos = ('Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen')

tens = ('Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety', 'Hundred')

suffixes = ('', 'Thousand', 'Million', 'Billion')

def get_num2words(self):
    return num2words(self.net_pay)