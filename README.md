## How to SETUP in Windows/MAC/Linux

    Clone this Project git clone https://github.com/zayyadi/paroll.git
    Go to Project Directory cd paroll
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
