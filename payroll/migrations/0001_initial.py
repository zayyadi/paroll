# Generated by Django 4.0.2 on 2022-11-21 20:44

import autoslug.fields
from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import monthyear.models
import payroll.generator


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='EmployeeProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('emp_id', models.CharField(default=payroll.generator.emp_id, editable=False, max_length=255, unique=True)),
                ('first_name', models.CharField(blank=True, max_length=255, null=True)),
                ('last_name', models.CharField(blank=True, max_length=255, null=True)),
                ('email', models.EmailField(blank=True, max_length=255)),
                ('photo', models.FileField(blank=True, default='default.png', null=True, upload_to='')),
                ('nin', models.CharField(default=payroll.generator.nin_no, editable=False, max_length=255, unique=True)),
                ('tin_no', models.CharField(default=payroll.generator.tin_no, editable=False, max_length=255, unique=True)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('date_of_employment', models.DateField(blank=True, null=True)),
                ('contract_type', models.CharField(blank=True, choices=[('P', 'Permanent'), ('T', 'Temporary')], max_length=1, null=True)),
                ('phone', models.CharField(blank=True, default=1234567890, max_length=15, unique=True, verbose_name='phone number')),
                ('gender', models.CharField(choices=[('others', 'Others'), ('male', 'Male'), ('female', 'Female')], default='others', max_length=255, verbose_name='gender')),
                ('address', models.CharField(blank=True, max_length=255, null=True, verbose_name='address')),
                ('created', models.DateTimeField(default=django.utils.timezone.now)),
                ('job_title', models.CharField(choices=[('C', 'Casual'), ('JS', 'Junior staff'), ('OP', 'Operator'), ('SU', 'SUpervisor'), ('M', 'Manager'), ('COO', 'C.O.O')], default='casual', max_length=255, verbose_name='designation')),
                ('bank', models.CharField(choices=[('Zenith', 'Zenith BANK'), ('Access', 'Access Bank'), ('GTB', 'GT Bank'), ('Jaiz', 'JAIZ Bank'), ('FCMB', 'FCMB'), ('FBN', 'First Bank'), ('Union', 'Union Bank'), ('UBA', 'UBA')], default='Z', max_length=10, verbose_name='employee BANK')),
                ('bank_account_name', models.CharField(blank=True, max_length=255, null=True, unique=True, verbose_name='Bank Account Name')),
                ('bank_account_number', models.CharField(blank=True, max_length=10, null=True, unique=True, verbose_name='Bank Account Number')),
                ('net_pay', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('status', models.CharField(choices=[('active', 'ACTIVE'), ('pending', 'PENDING')], default='pending', max_length=10)),
            ],
            options={
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='Payday',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
        ),
        migrations.CreateModel(
            name='Payroll',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('basic_salary', models.DecimalField(decimal_places=2, max_digits=12)),
                ('basic', models.DecimalField(blank=True, decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('housing', models.DecimalField(blank=True, decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('transport', models.DecimalField(blank=True, decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('bht', models.DecimalField(blank=True, decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('pension_employee', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('pension_employer', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('pension', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('gross_income', models.DecimalField(blank=True, decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('consolidated_relief', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('taxable_income', models.DecimalField(blank=True, decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('payee', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('water_rate', models.DecimalField(blank=True, decimal_places=2, default=Decimal('200'), max_digits=12)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('active', 'ACTIVE'), ('pending', 'PENDING')], default='pending', max_length=10)),
            ],
        ),
        migrations.CreateModel(
            name='PayVar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_absent', models.BooleanField(default=False)),
                ('is_late', models.BooleanField(default=False)),
                ('is_loan', models.BooleanField(default=False)),
                ('is_coop', models.BooleanField(default=False)),
                ('lateness', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('absent', models.DecimalField(blank=True, decimal_places=2, max_digits=12)),
                ('damage', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('loan', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('coop', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('netpay', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12)),
                ('status', models.CharField(choices=[('active', 'ACTIVE'), ('pending', 'PENDING')], default='pending', max_length=10)),
                ('pays', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pays', to='payroll.employeeprofile')),
            ],
        ),
        migrations.CreateModel(
            name='PayT',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='test', max_length=50, unique=True)),
                ('slug', autoslug.fields.AutoSlugField(always_update=True, editable=True, populate_from='name')),
                ('paydays', monthyear.models.MonthField(help_text='some help...', null=True, verbose_name='Month Value')),
                ('is_active', models.BooleanField(default=False)),
                ('payroll_payday', models.ManyToManyField(related_name='payroll_payday', through='payroll.Payday', to='payroll.PayVar')),
            ],
            options={
                'verbose_name_plural': 'PayTs',
            },
        ),
        migrations.AddField(
            model_name='payday',
            name='paydays_id',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pay', to='payroll.payt'),
        ),
        migrations.AddField(
            model_name='payday',
            name='payroll_id',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payroll_paydays', to='payroll.payvar'),
        ),
        migrations.AddField(
            model_name='employeeprofile',
            name='employee_pay',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='employee_pay', to='payroll.payroll'),
        ),
        migrations.CreateModel(
            name='Allowance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, verbose_name='Name of allowance to be added')),
                ('amount', models.DecimalField(decimal_places=2, default=0.0, max_digits=12, verbose_name='Amount of allowance earned')),
                ('payr', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variable_payroll', to='payroll.employeeprofile')),
            ],
            options={
                'verbose_name_plural': 'Allowance',
            },
        ),
    ]
