## How to SETUP in Windows/MAC/Linux

Clone this Project git clone https://github.com/zayyadi/paroll.git

    Go to Project Directory 

        `cd paroll`

    Create a Virtual Environment :-
        for Windows python -m venv env
            for Linux/Mac python3 -m venv env
        Activate Virtual Environment source env/bin/activate for linux
        Activate Virtual Environment source env/Script/activate
        Install Requirment Packages pip install -r requirments.txt
        Migrate Database :-
            For Windows py manage.py migrate
            For Linux/Mac python3 manage.py migrate
        Create SuperUser :-
            For Windows py manage.py createsuperuser
            For Linux/Mac python3 manage.py createsuperuser
        Finally Run the Projects :-
            For Windows py manage.py runserver
            For Linux/Mac python3 manage.py runserver

This django project is based on the Nigerian Tax code and most parameter used are reflective of that.

This system is built for payroll administrator to setup the payroll effectivly, there are various functionalities implemented for both the admin and the user. these include:

    1. Allowance Services.
       * Add allowance to system.
       * Add allowance for employee.
       * Cancel allowance.

    2. Generic Services
      * View Benefits — View various benefits available to the user.
      * Generate payroll.
      * Pay Slip download

    3. Generate Reports
      * Monthly Employee Tax Schedule.
