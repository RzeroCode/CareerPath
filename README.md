# CareerPath
This project aims to guide its users' career paths. The user will enter their career choice in a query system, the algorithm will calculate a suitable career path based
on collected career data in its database. Each meaningful query has its unique score based algorithm in the backend side of the application. Frontend side will get this
response from the backend and display it to the user in a meaningful table-like format.

You can see the input screen with an example query below, this image also shows autocomplete algorithm, which autocompletes user inputs based on system data:
![Image of Input Screen](https://raw.githubusercontent.com/RzeroCode/CareerPath/main/images/input_screen.png)


There are 5 types of queries which user can enter, the user just has to leave other input fields blank (*Pink ones are user inputs, green ones are algorithm outputs*):


![Image of Queries](https://raw.githubusercontent.com/RzeroCode/CareerPath/main/images/queries.png)

Below you can see the output screen of an example query: *"I want to study computer science at Koc University which career related skills will I gain from it and 
which work profession in which company I will likely end up forking for?"*:
![Image of Output Screen](https://raw.githubusercontent.com/RzeroCode/CareerPath/main/images/output_screen.png)


**As you can see in the image some skills have marks on them, indicating they are currently trending skills according to the algorithm.**

*A 25 page lengthy scientific report will be provided if asked, it includes how the scoring algorithm works, how is data collected, formatted and background of the project.*


## Installation
* Python 3 must be installed to the device, please refer to the [link to Python](https://www.python.org/downloads/)
* Django must be installed on the device, you can install it using `pip install Django` alternatively, refer to the [link to Django](https://www.djangoproject.com/)
* Postgresql must be installed, refer to the
