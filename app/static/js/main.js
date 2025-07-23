document.addEventListener("DOMContentLoaded", function(){
    window.addEventListener('scroll', function() {
        if (window.scrollY > 80) {
          document.getElementById('navbar_top').classList.add('fixed-top');
          // add padding top to show content behind navbar
          navbar_height = document.querySelector('.navbar').offsetHeight;
          // document.body.style.paddingTop = navbar_height + 'px';
        } else {
          document.getElementById('navbar_top').classList.remove('fixed-top');
           // remove padding top from body
          document.body.style.paddingTop = '0';
        } 
    });
  }); 
  // DOMContentLoaded  end

 
$(document).ready(function() {
  $( '.carosel.partner' ).each( function() {
      $( this ).slick( {
      infinite: true,
      autoplay: true,
      autoplaySpeed: 3000,
      // this value should < total # of slides, otherwise the carousel won't slide at all
      slidesToShow: 6,
      slidesToScroll: 1,
      speed: 2000,
      dots: false,
      arrows: false,
      prevArrow: '<button class="slide-arrow prev-arrow"></button>',
      nextArrow: '<button class="slide-arrow next-arrow"></button>',

      responsive: [
          {
            breakpoint: 1024,
            settings: {
              slidesToShow: 3,
              slidesToScroll: 1,
            }
          },
          {
            breakpoint: 600,
            settings: {
              slidesToShow: 2,
              slidesToScroll: 1,
            }
          },
          {
            breakpoint: 480,
            settings: {
              slidesToShow: 2,
              slidesToScroll: 1,
            }
          }
        ]
  } );
} );
} );

$(document).ready(function() {
  $( '.testi' ).each( function() {
      $( this ).slick( {
      infinite: true,
      autoplay: true,
      autoplaySpeed: 3000,
      // this value should < total # of slides, otherwise the carousel won't slide at all
      slidesToShow: 2,
      slidesToScroll: 1,
      speed: 2000,
      dots: false,
      arrows: true,
      prevArrow: '<button class="prev-arrow"><i class="fa fa-angle-left"></button>',
      nextArrow: '<button class="next-arrow"><i class="fa fa-angle-right"></button>',

      responsive: [
          {
            breakpoint: 1024,
            settings: {
              slidesToShow: 2,
              slidesToScroll: 1,
            }
          },
          {
            breakpoint: 600,
            settings: {
              slidesToShow: 1,
              slidesToScroll: 1,
            }
          },
          {
            breakpoint: 480,
            settings: {
              slidesToShow: 1,
              slidesToScroll: 1,
            }
          }
        ]
  } );
} );
} );


AOS.init();

$(document).ready(function(){

  $(".filter-button").click(function(){
      var value = $(this).attr('data-filter');
      
      if(value == "all")
      {
          //$('.filter').removeClass('hidden');
          $('.filter').show('1000');
      }
      else
      {
          $(".filter").not('.'+value).hide('3000');
          $('.filter').filter('.'+value).show('3000');   
      }

      if ($(".filter-button").removeClass("active")) {
        $(this).removeClass("active");
      }
      $(this).addClass("active");

  });
  

});

// back to top
//Get the button
var mybutton = document.getElementById("backTop");

// When the user scrolls down 20px from the top of the document, show the button
window.onscroll = function() {scrollFunction()};

function scrollFunction() {
  if (document.body.scrollTop > 250 || document.documentElement.scrollTop > 250) {
    mybutton.style.display = "block";
  } else {
    mybutton.style.display = "none";
  }
}

// When the user clicks on the button, scroll to the top of the document
function topFunction() {
  document.body.scrollTop = 0;
  document.documentElement.scrollTop = 0;
}


// counter
function makeTimer() {

	//		var endTime = new Date("29 April 2018 9:56:00 GMT+01:00");	
		var endTime = new Date("26 June 2024 9:56:00 GMT+01:00");			
			endTime = (Date.parse(endTime) / 1000);

			var now = new Date();
			now = (Date.parse(now) / 1000);

			var timeLeft = endTime - now;

			var days = Math.floor(timeLeft / 86400); 
			var hours = Math.floor((timeLeft - (days * 86400)) / 3600);
			var minutes = Math.floor((timeLeft - (days * 86400) - (hours * 3600 )) / 60);
			var seconds = Math.floor((timeLeft - (days * 86400) - (hours * 3600) - (minutes * 60)));
  
			if (hours < "10") { hours = "0" + hours; }
			if (minutes < "10") { minutes = "0" + minutes; }
			if (seconds < "10") { seconds = "0" + seconds; }

			$("#days").html(days + "<span>Days</span>");
			$("#hours").html(hours + "<span>Hours</span>");
			$("#minutes").html(minutes + "<span>Minutes</span>");
			$("#seconds").html(seconds + "<span>Seconds</span>");		

	}

	setInterval(function() { makeTimer(); }, 1000);


// onload 

$( window ).on( "load", function() {
  $(".loader").delay(2000).slideUp("slow");
  $("#overlayer").delay(2000).slideUp("slow");
});


// contact form
function ValidateEmail(email) {
  // alert(1);
  var expr = /^([\w-\.]+)@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.)|(([\w-]+\.)+))([a-zA-Z]{2,4}|[0-9]{1,3})(\]?)$/;
  return expr.test(email);
};

$("#demoContact").click(function() {
  if(!ValidateEmail($("#txtcontact").val())) {
    $("#error").addClass("error-msg-contact-display");
  } else {
    $("#error").removeClass("error-msg-contact-display");
    // $( "#success" ).addClass("success-msg-contact-display");
    $("#success").addClass("success-msg-contact-display").delay(3000).queue(function() {
      $(this).removeClass("success-msg-contact-display").dequeue();
    });
  }

});

// contact form 1
function ValidateEmail1(email) {
  // alert(1);
  var expr = /^([\w-\.]+)@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.)|(([\w-]+\.)+))([a-zA-Z]{2,4}|[0-9]{1,3})(\]?)$/;
  return expr.test(email);
};

$("#demoContact1").click(function() {
  if(!ValidateEmail1($("#txtcontact1").val())) {
    $("#error1").addClass("error-msg-contact-display");
  } else {
    $("#error1").removeClass("error-msg-contact-display");
    // $( "#success" ).addClass("success-msg-contact-display");
    $("#success1").addClass("success-msg-contact-display").delay(3000).queue(function() {
      $(this).removeClass("success-msg-contact-display").dequeue();
    });
  }

});

AOS.init();