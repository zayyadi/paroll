# # ones = ('Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine')

# # twos = ('Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen')

# # tens = ('Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety', 'Hundred')

# # suffixes = ('', 'Thousand', 'Million', 'Billion')

# # def process(number, index):
    
# #     if number=='0':
# #         return 'Zero'
    
# #     length = len(number)
    
# #     if(length > 3):
# #         return False
    
# #     number = number.zfill(3)
# #     words = ''
 
# #     hdigit = int(number[0])
# #     tdigit = int(number[1])
# #     odigit = int(number[2])
    
# #     words += '' if number[0] == '0' else ones[hdigit]
# #     words += ' Hundred ' if not words == '' else ''
    
# #     if(tdigit > 1):
# #         words += tens[tdigit - 2]
# #         words += ' '
# #         words += ones[odigit]
    
# #     elif(tdigit == 1):
# #         words += twos[(int(tdigit + odigit) % 10) - 1]
        
# #     elif(tdigit == 0):
# #         words += ones[odigit]

# #     if(words.endswith('Zero')):
# #         words = words[:-len('Zero')]
# #     else:
# #         words += ' '
     
# #     if(not len(words) == 0):    
# #         words += suffixes[index]
        
# #     return words;
    
# # def getWords(number):
# #     length = len(str(number))
    
# #     if length>12:
# #         return 'This program supports upto 12 digit numbers.'
    
# #     count = length // 3 if length % 3 == 0 else length // 3 + 1
# #     copy = count
# #     words = []
 
# #     for i in range(length - 1, -1, -3):
# #         words.append(process(str(number)[0 if i - 2 < 0 else i - 2 : i + 1], copy - count))
# #         count -= 1;

# #     final_words = ''
# #     for s in reversed(words):
# #         temp = s + ' '
# #         final_words += temp
    
# #     return final_words

# # number = int(input('Enter any number: '))
# # print('%d in words is: %s' %(number, getWords(number)),"naira only")

# import math
 
# # Tokens from 1000 and up
# _PRONOUNCE = [
#     'vigintillion',
#     'novemdecillion',
#     'octodecillion',
#     'septendecillion',
#     'sexdecillion',
#     'quindecillion',
#     'quattuordecillion',
#     'tredecillion',
#     'duodecillion',
#     'undecillion',
#     'decillion',
#     'nonillion',
#     'octillion',
#     'septillion',
#     'sextillion',
#     'quintillion',
#     'quadrillion',
#     'trillion',
#     'billion',
#     'million',
#     'thousand',
#     ''
# ]
 
# # Tokens up to 90
# _SMALL = {
#     '0' : '',
#     '1' : 'one',
#     '2' : 'two',
#     '3' : 'three',
#     '4' : 'four',
#     '5' : 'five',
#     '6' : 'six',
#     '7' : 'seven',
#     '8' : 'eight',
#     '9' : 'nine',
#     '10' : 'ten',
#     '11' : 'eleven',
#     '12' : 'twelve',
#     '13' : 'thirteen',
#     '14' : 'fourteen',
#     '15' : 'fifteen',
#     '16' : 'sixteen',
#     '17' : 'seventeen',
#     '18' : 'eighteen',
#     '19' : 'nineteen',
#     '20' : 'twenty',
#     '30' : 'thirty',
#     '40' : 'forty',
#     '50' : 'fifty',
#     '60' : 'sixty',
#     '70' : 'seventy',
#     '80' : 'eighty',
#     '90' : 'ninety'
# }
 
# def get_num(num):
#     '''Get token <= 90, return '' if not matched'''
#     return _SMALL.get(num, '')
 
# def triplets(l):
#     '''Split list to triplets. Pad last one with '' if needed'''
#     res = []
#     for i in range(int(math.ceil(len(l) / 3.0))):
#         sect = l[i * 3 : (i + 1) * 3]
#         if len(sect) < 3: # Pad last section
#             sect += [''] * (3 - len(sect))
#         res.append(sect)
#     return res
 
# def norm_num(num):
#     """Normelize number (remove 0's prefix). Return number and string"""
#     n = int(num)
#     return n, str(n)
 
# def small2eng(num):
#     '''English representation of a number <= 999'''
#     n, num = norm_num(num)
#     hundred = ''
#     ten = ''
#     if len(num) == 3: # Got hundreds
#         hundred = get_num(num[0]) + ' hundred'
#         num = num[1:]
#         n, num = norm_num(num)
#     if (n > 20) and (n != (n / 10 * 10)): # Got ones
#         tens = get_num(num[0] + '0')
#         ones = get_num(num[1])
#         ten = tens + ' ' + ones
#     else:
#         ten = get_num(num)
#     if hundred and ten:
#         return hundred + ' ' + ten
#         #return hundred + ' and ' + ten
#     else: # One of the below is empty
#         return hundred + ten
 
# def num2eng(num):
#     '''English representation of a number'''
#     num = str(num) # Convert to string, throw if bad number
#     if (len(num) / 3 >= len(_PRONOUNCE)): # Sanity check
#         raise ValueError('Number too big')
 
#     if num == '0': # Zero is a special case
#         return 'zero '
 
#     # Create reversed list
#     x = list(num)
#     x.reverse()
#     pron = [] # Result accumolator
#     ct = len(_PRONOUNCE) - 1 # Current index
#     for a, b, c in triplets(x): # Work on triplets
#         p = small2eng(c + b + a)
#         if p:
#             pron.append(p + ' ' + _PRONOUNCE[ct])
#         ct -= 1
#     # Create result
#     pron.reverse()
#     return ', '.join(pron)
 
# if __name__ == '__main__':
    
#     numbers = [1.37, 0.07, 123456.00, 987654.33]
#     for number in numbers:
#         naira, kobo = [int(num) for num in str(number).split(".")]
    
#         naira = num2eng(naira)
#         if naira.strip() == "one":
#             naira = naira + "naira and "
#         else:
#             naira = naira + "naira and "
            
#         kobo = num2eng(kobo) + "kobo"
#         print( naira + kobo)
#         temp_amount = str(10.34)
#         if '.' in temp_amount:
#             amount = temp_amount.split('.')
#             dollars = amount[0]
#             cents = amount[1]
#         else:
#             dollars = temp_amount
#             cents = '00'
#         amt = num2eng(dollars)
#         total = amt + 'and %s/100 Dollars' % cents
#         print (total)

# var_sum = Payday.objects.filter(paydays_id_id=pay_id)
    # pay = PayT.objects.filter(is_active=True,payroll_payday=var)
#     # pay = None
    # for id in pay_id:
    # if id in var.payroll_id_id:
    #     print(pay_id)
    #     return id
#     # if pay_id:
#     #     pay = get_object_or_404(VariableCalc, var_id=pay_id)
#     #     var = PayT.objects.filter(payroll_payday__in[pay])

# ls1 = [12,1,2,3,4,5,6,7]
# ls2 = [12,3,4,78,1,4]

# for elem in ls2:
#     if elem in ls1:
#         print(elem)

from collections import namedtuple

class Car:
    def __init__(self, name, v_type) -> None:
        self.name = name
        self.type = v_type
        self.add_ons = []

    def add_ons(self, name,color,placement):
        AddOn = namedtuple("AddOn", "name color placement")
        add_on = AddOn(name,color,placement)
        self.add_ons.append(add_on)
        return add_on
    