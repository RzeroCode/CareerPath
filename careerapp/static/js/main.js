// consts

let universities = [];
let company = [];
let fields = [];
let whatdo = [];
let skills = [];
let arrs = ["input-uni", "input-company", "input-job", "input-degree", "input-skills"];

document.getElementById('submit-query').addEventListener('click', (e) => {
    let uni = document.getElementById('input-uni').value;
    let comp = document.getElementById('input-company').value;
    let job = document.getElementById('input-job').value;
    let degree = document.getElementById('input-degree').value;
    let skills = document.getElementById('input-skills').value;
    let type = typeOfQuery();
    if (type < 0) {
        console.log('Problem with the type');
        return
    }
    document.getElementById("results-row").innerHTML = "";

    data = {
        'uni': uni,
        'comp': comp,
        'job': job,
        'degree': degree,
        'skills': skills,
    };

    fetch(`API/query/${type}`, {
        method: 'POST',
        body: JSON.stringify(data)
    }).then((response) => {
        if (response.status != 200) {
            console.log("There was an error with the request.");
            return null;
        }
        return response.text();
    }).then((text) => {
        let res = JSON.parse(text);
        for (var prop in res) {
            if (Object.prototype.hasOwnProperty.call(res, prop)) {
                createTableFromData(res[prop], prop);
            }
        }
    });

});

function typeOfQuery() {
    let queryType = -1;
    let uni = document.getElementById("input-uni").value
    let comp = document.getElementById("input-company").value
    let job = document.getElementById("input-job").value
    let degree = document.getElementById("input-degree").value
    let skills = document.getElementById("input-skills").value

    if (degree !== "" && comp !== "" && uni === "" && job === "" && skills === "") {
        queryType = 0
    } else if (comp !== "" && job !== "" && uni === "" && degree === "" && skills === "") {
        queryType = 1
    } else if (uni !== "" && degree !== "" && comp === "" && job === "" && skills === "") {
        queryType = 2
    } else if (uni !== "" && skills !== "" && degree !== "" && job === "" && comp === "") {
        queryType = 3
    } else if (comp !== "" && skills === "" && degree === "" && job === "" && uni === "") {
        queryType = 4
    } else {
        document.getElementById("alert").style = `visibility:visible;display:flex;justify-content:center;margin-top:10px`;
        return
    }
    document.getElementById("alert").style = `visibility:hidden;display:flex;justify-content:center;margin-top:10px`;
    return queryType;

}

function myFunction() {
    alert("Page is loaded");
}

function createTable(data) {
    let tableString = ``;
    setTrend = false
    trendCount = 0;
    for (let index = 0; index < data.length; index++) {
        tableString += setTrend ? '': `<tr><th>${index + 1 - trendCount}</th>`
        const element = data[index];
        for (const item of element) {
            if(item == 'trend') {
                setTrend = true;
                trendCount+=1;
                continue;
            }
            tableString += `<td>${item}</td>`;
            
            tableString += `<td style="color:#00cc00">${setTrend?'▲🚀🙌🔥':''}</td>`
            
            setTrend = false
        }

        tableString += setTrend ? '': `</tr>`;
    }
    return tableString
}

function createTableFromData(data, name) {
    let body = '';
    let tableName = '';
    switch (name) {
        case 'uni':
            console.log('handle uni');
            tableName = 'Prestigious Universities chosen for your dream';
            break;
        case 'comp':
            console.log('handle company');
            tableName = 'Companies that are likely to employ you.'
            break;
        case 'field':
            console.log('handle field');
            tableName = `Possible fields of study to achieve your dream...`
            break;
        case 'do':
            console.log('handle do');
            tableName = `Departments that are in high demand...`
            break;
        case 'skill':
            console.log('handle skill');
            tableName = `Skills that will increase your chances...`
            break;
        default:
            console.log(`wtf? ${name}`);
            tableName = 'fix error';
            body = 'There was an error. Fix it';
            break;
    }
    body = createTable(data);
    tableTemplate = `<div class="col-lg-8 mx-auto" onshow="myFunction()"><h2>${tableName}</h2>
    <table class="table table-hover">
    <tbody>${body}</tbody></table>
    </div>`;
    tableNode = document.createElement("div")
    tableNode.innerHTML = tableTemplate;
    document.getElementById("results-row").appendChild(tableNode.firstChild)
}

function autoComplete(inp, arr) {
    /*the autocomplete function takes two arguments,
    the text field element and an array of possible autocompleted values:*/
    var currentFocus;
    /*execute a function when someone writes in the text field:*/
    inp.addEventListener("input", function(e) {
        var a, b, i, val = this.value;
        /*close any already open lists of autocompleted values*/
        closeAllLists();
        if (!val) { return false; }
        if (e.target.id == "input-skills") {
            val = val.split(',').pop()
        }
        currentFocus = -1;
        /*create a DIV element that will contain the items (values):*/
        a = document.createElement("DIV");
        a.setAttribute("id", this.id + "autocomplete-list");
        a.setAttribute("class", "autocomplete-items");
        /*append the DIV element as a child of the autocomplete container:*/
        this.parentNode.appendChild(a);
        /*for each item in the array...*/
        for (i = 0; i < arr.length; i++) {
            /*check if the item starts with the same letters as the text field value:*/
            if (arr[i].substr(0, val.length).toUpperCase() == val.toUpperCase()) {
                /*create a DIV element for each matching element:*/
                b = document.createElement("DIV");
                /*make the matching letters bold:*/
                b.innerHTML = "<strong>" + arr[i].substr(0, val.length) + "</strong>";
                b.innerHTML += arr[i].substr(val.length);
                /*insert a input field that will hold the current array item's value:*/
                b.innerHTML += "<input type='hidden' value='" + arr[i] + "'>";
                /*execute a function when someone clicks on the item value (DIV element):*/
                b.addEventListener("click", function(e) {
                    /*insert the value for the autocomplete text field:*/
                    inp.value = inp.id == "input-skills" ? `${inp.value.substr(0,inp.value.lastIndexOf(','))}${inp.value.lastIndexOf(',')==-1?'':','}${this.getElementsByTagName("input")[0].value}` : this.getElementsByTagName("input")[0].value;
                    /*close the list of autocompleted values,
                    (or any other open lists of autocompleted values:*/
                    closeAllLists();
                });
                a.appendChild(b);
            }
        }
    });
    /*execute a function presses a key on the keyboard:*/
    inp.addEventListener("keydown", function(e) {
        var x = document.getElementById(this.id + "autocomplete-list");
        if (x) x = x.getElementsByTagName("div");
        if (e.keyCode == 40) {
            /*If the arrow DOWN key is pressed,
            increase the currentFocus variable:*/
            currentFocus++;
            /*and and make the current item more visible:*/
            addActive(x);
        } else if (e.keyCode == 38) { //up
            /*If the arrow UP key is pressed,
            decrease the currentFocus variable:*/
            currentFocus--;
            /*and and make the current item more visible:*/
            addActive(x);
        } else if (e.keyCode == 13) {
            /*If the ENTER key is pressed, prevent the form from being submitted,*/
            e.preventDefault();
            if (currentFocus > -1) {
                /*and simulate a click on the "active" item:*/
                if (x) x[currentFocus].click();
            }
        }
    });

    function addActive(x) {
        /*a function to classify an item as "active":*/
        if (!x) return false;
        /*start by removing the "active" class on all items:*/
        removeActive(x);
        if (currentFocus >= x.length) currentFocus = 0;
        if (currentFocus < 0) currentFocus = (x.length - 1);
        /*add class "autocomplete-active":*/
        x[currentFocus].classList.add("autocomplete-active");
    }

    function removeActive(x) {
        /*a function to remove the "active" class from all autocomplete items:*/
        for (var i = 0; i < x.length; i++) {
            x[i].classList.remove("autocomplete-active");
        }
    }

    function closeAllLists(elmnt) {
        /*close all autocomplete lists in the document,
        except the one passed as an argument:*/
        var x = document.getElementsByClassName("autocomplete-items");
        for (var i = 0; i < x.length; i++) {
            if (elmnt != x[i] && elmnt != inp) {
                x[i].parentNode.removeChild(x[i]);
            }
        }
    }
    /*execute a function when someone clicks in the document:*/
    document.addEventListener("click", function(e) {
        closeAllLists(e.target);
    });
}

for (let index = 0; index < 5; index++) {
    fetch(`API/auto-complete/${index}`, {
        method: 'POST',
    }).then((response) => {
        if (response.status != 200) {
            console.log("There was an error with the request.");
            return null;
        }
        return response.text();
    }).then((text) => {
        autoComplete(document.getElementById(arrs[index]), JSON.parse(text));
    });
}