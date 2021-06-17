(function($) {
  "use strict"; // Start of use strict

  // Smooth scrolling using jQuery easing
  $('a.js-scroll-trigger[href*="#"]:not([href="#"])').click(function() {
    if (location.pathname.replace(/^\//, '') == this.pathname.replace(/^\//, '') && location.hostname == this.hostname) {
      var target = $(this.hash);
      target = target.length ? target : $('[name=' + this.hash.slice(1) + ']');
      if (target.length) {
        $('html, body').animate({
          scrollTop: (target.offset().top - 56)
        }, 1000, "easeInOutExpo");
        return false;
      }
    }
  });

  // Closes responsive menu when a scroll trigger link is clicked
  $('.js-scroll-trigger').click(function() {
    $('.navbar-collapse').collapse('hide');
  });

  // Activate scrollspy to add active class to navbar items on scroll
  $('body').scrollspy({
    target: '#mainNav',
    offset: 56
  });
  function createGist(opts) {
    ChromeSamples.log('Posting request to GitHub API...');
    fetch('https://api.github.com/gists', {
      method: 'post',
      body: JSON.stringify(opts)
    }).then(function(response) {
      return response.json();
    }).then(function(data) {
      ChromeSamples.log('Created Gist:', data.html_url);
    });
  }
  
  function submitGist() {
    var content = document.querySelector('textarea').value;
    if (content) {
      createGist({
        description: 'Fetch API Post example',
        public: true,
        files: {
          'test.js': {
            content: content
          }
        }
      });
    } else {
      ChromeSamples.log('Please enter in content to POST to a new Gist.');
    }
  }
  
  var submitBtn = document.querySelector('button');
  submitBtn.addEventListener('click', submitGist);

})(jQuery); // End of use strict
