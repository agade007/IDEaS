#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import webapp2
import cgi
import csv
import urllib2
import string
import random
import struct

from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import mail
from google.appengine.api import users
from datetime import datetime, timedelta
from google.appengine.ext import ndb
from google.appengine.api import urlfetch
from google.appengine.runtime import apiproxy_errors
from webapp2_extras import sessions
from google.appengine.api import taskqueue
#from sendgrid import SendGridClient
#from sendgrid import Mail

# Databases and keys
DEFAULT_DATABASE_NAME = "PROOF_LAB_DATA"
engineers = ["bgebre", "msimono"]
statelist = ["Processing Quote", "Awaiting Advisor", "Authorized", "Revisions", "Scheduled","Delivered","Closed","Withdrawn"]
materialslist = ["No Preference","PLA", "ABS", "Connex-Composite"]
machineslist = ["Maker-1", "Maker-2", "Mojo-1", "Mojo-2", "Mojo-3", "U Print","Dimension","Objet Connex "  ]
# this is $/cm^3 - $2 in^3, $6 in^3 and $15 in^3
costlist =     [0.30,0.30,0.60,0.60,0.60,0.60,0.60,0.90]
adminslist = ["biruk.gebre@gmail.com","kishore.stevens@gmail.com","msimonov@stevens.edu","SIT.Protolabs@gmail.com"]
SETUPCOST = 5

class SystemStateDB(ndb.Model):
    systemstate = ndb.IntegerProperty(required=False)
    systemversion = ndb.IntegerProperty(required=False)
#System state 0 : Normal; 1: Updating: 2:Maintentance

class UserDB(ndb.Model):
    email = ndb.StringProperty(required=True )  #uemail
    name = ndb.StringProperty(required=True)    #uname
    created = ndb.DateTimeProperty(auto_now_add=True)
    accesscode = ndb.StringProperty(required=True) #ucode

class LabJobsDB(ndb.Model):
    useremail = ndb.StringProperty(required=True)
    description= ndb.StringProperty(required=True)
    userkey = ndb.StringProperty(required=True)
    filename = ndb.StringProperty(required=True)
    advisorname = ndb.StringProperty(required=True)
    advisoremail = ndb.StringProperty(required=True)
    sdsection = ndb.StringProperty(required=True)  #usection
    projectname = ndb.StringProperty(required=True) #uproject
    lastmodified = ndb.DateTimeProperty(required=False)
    stlblobkey = ndb.StringProperty(required=True)
    boundingbox = ndb.StringProperty(required=True)
    partvolume = ndb.StringProperty(required=True)
    supportvolume = ndb.StringProperty(required=False)
    partmaterial = ndb.StringProperty(required=False)
    #
    state=ndb.IntegerProperty(required=True)
            # 0. Processing Estimate 1. Waiting Advisor 2. Authorized; 3. Revisions 4. Scheduled 5. Delivered 6. Closed
    engineer = ndb.StringProperty(required=False )
    machineassigned = ndb.StringProperty(required=False )
    costtolab = ndb.StringProperty(required=False )
                    #time stamps
    created = ndb.DateTimeProperty(auto_now_add=True)
    authorized = ndb.DateTimeProperty(required=False)
    reviewed = ndb.DateTimeProperty(required=False)
    scheduled = ndb.DateTimeProperty(required=False)
    delivered = ndb.DateTimeProperty(required=False)
    jobidcode = ndb.StringProperty(required=False)

class ReviewTracking(ndb.Model):
    useremail = ndb.StringProperty(required=True)
    message   = ndb.StringProperty(required=True)
    created   = ndb.DateTimeProperty(auto_now_add=True)
    jobid = ndb.StringProperty(required=True)
    adminid = ndb.StringProperty(required=True)
    state = ndb.IntegerProperty(required=True)

HEADER_STRING1 = """
# -*- coding: utf-8 -*-    
    <!DOCTYPE html>
    <html>
    <head>
    <title>Proof Lab Job Requests </title>
    <meta charset="UTF-8" />
    <link rel="stylesheet" href="http://css/style.css" />
    </head>
    <body>
    <table width=95% id="table-3"> 
    <tr>
    <td width =20% align="center" style="vertical-align:middle" ><IMG src="https://www.stevens.edu/sites/all/themes/stevens/images/favicons/favicon-194x194.png"      height=150> </td>
    <td width =70% align="center" style="vertical-align:middle" > <H1>
    Innovation, Design and Entrepreneurship (IDEaS) Program <BR> Prototype Object Fabrication (PROOF) Laboratory  </H1>
    <H2> Carnegie 1st Floor, Stevens Institute of Technology<BR> Hoboken, NJ 07030 </H2> </td> </tr>
    <tr> <td width =30% valign="top"> <h2> Useful Links </h2>
    <ul>
    <li> <A Href="/assets/instructions.pdf" style="color:red"> Job Submission and Delivery Process </A> </li>
    <li> <A Href="/assets/prooflab-machines.pdf" style="color:red"> Printers in the lab </A> </li>
    <li> Material Property Datasheets</li>
    <ul>
    <li><A Href="/assets/PJ-full-pallette.pdf" style="color:red"> Objet Full Pallette </A> </li>
    <li><A Href="/assets/polyjet_materials_data.pdf" style="color:red"> Polyjet Materials </A> </li>
    <li><A Href="/assets/digital-materials.pdf" style="color:red"> Objet Digital Materials </A> </li>
    <li><A Href="/assets/absplus.pdf" style="color:red"> Mojo/U-Print/Dimension (FDM) ABS+ </A> </li>
    <li><A Href="/assets/makerbot-pla-abs.pdf" style="color:red"> Makerbot PLA and ABS </A> </li>
    <li><A Href="http://www.stratasys.com/materials/material-safety-data-sheets" style="color:red"> MSDS for all Stratasys Materials </A> </li>
    </ul>
    <li> Reduce the cost of materials with appropriate <A HREF="/assets/infill.jpg"> infill. </A>
    <li> Cost guide for lab printers:
         <ul>
         <li> Setup cost (minimum charge) : $5 +
         <li> <A href="https://store.makerbot.com/replicator2.html" style="color:blue" >  Makerbot </A>: $2 per in^3 </li>
         <li> <A href="http://www.stratasys.com/3d-printers/idea-series/mojo" style="color:blue" > Mojo </A> |
          <A href="http://www.stratasys.com/3d-printers/design-series/dimension-1200es" style="color:blue" > Dimension </A>|
          <A href="http://www.stratasys.com/3d-printers/idea-series/uprint-se" style="color:blue" > U Print </A> : $6 per in^3   </li>
         <li> <A href="http://www.stratasys.com/3d-printers/production-series/connex3-systems" style="color:blue" >  Objet Connex350</A>: $15 per in^3  </li>
         </ul>
         <li> <A href="http://lazarsoft.info/objstl/#" style="color:"blue"> STL File Viewer </A> </li>
         <li> <A href="http://gcode.ws/" style="color:"blue"> G-Code Viewer  </A> </li>
         <li> <A href="http://www.greentoken.de/onlineconv/" style="color:"blue"> Convert File Format </A> </li>
         <li> <A Href="http://www.shapeways.com/tutorials/easy-3d-modeling-for-3d-printing-tutorial-for-beginners" style="color:red"> Guide to 3D Printing </A>  </li>
         <li> <A Href="http://www.3dpartprice.com/" style="color:red"> Estimate rough cost here </A> <BR> <B> Guide only and not an actual quote </B>   </li>
         <li> So we can't print what you want? <a href="https://www.3dhubs.com/"> Try here. </A>
    </ul>
    <p align="left">
    <A HREF="http://proof-lab-jobrequests.appspot.com" style="color:blue"> Login Page  </A> </P>
    <p align="left">
    <A HREF="http://proof-lab-jobrequests.appspot.com/admin" style="color:blue" > Admin Access  </A> </P>
    </td>
    <td width = 70%>
    """

FOOTER_STRING1 = """ </td> </tr> </table> </center>
    </body>
    </html>"""

HEADER_STRING="""
<!DOCTYPE html>
<html lang='eng'>
<head>
    <meta charset="utf-8">
    <meta http-equiv="x-ua-compatible" content="ie=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <title>Innovation, Design and Entrepreneurship (IDEaS) | Stevens Institute of Technology</title>
    <link type="text/css" rel="stylesheet" href="/css/style.css" />
    <link type="text/css" rel="stylesheet" href="https://fast.fonts.net/cssapi/d0b486e3-1465-45e2-b0d2-2f285e3dd330.css"/>
    <link rel="stylesheet" href="http://www.stevens.edu/sites/all/themes/stevens/css/site.css?t=201701121240"/>
</head>
<div class="header_push_mobile"></div>
<div class="site_alert_placeholder"></div>
<header id="header" class="header" role="banner">
    <div class="header_container">

        <a href="https://www.stevens.edu" class="header_site_link">
            <div class="header_chevron"></div>
            <div class="header_logo">
                <img src="http://www.stevens.edu/sites/all/themes/stevens/images/bw_logo.png" alt="Stevens Institute of Technology - The Innovation University®" width="320" height="140" >
            </div>
        </a>
<div class="secondary_nav">
                <div class="secondary_nav_item nav_hover nav_button_hover">
                </div>
                <div class="secondary_nav_item nav_hover nav_button_hover">
                    </div>
                <div class="secondary_nav_item nav_hover nav_button_hover">
                                     </div>

                <div class="secondary_nav_item nav_hover nav_button_hover">
                   <div class="search_dropdown search_module">
                        <form class="search_form"
                              action="/research-entrepreneurship/innovation-entrepreneurship/ideas-proof-lab"
                              method="post" id="search-block-form" accept-charset="UTF-8">
                            <div>
                                <div class="container-inline">
                                    <h2 class="element-invisible">Search form</h2>
                                    <div class="form-item form-type-textfield form-item-search-block-form">
                                        <label class="element-invisible" for="edit-search-block-form--2">Search </label>
                                        <input title="Enter the terms you wish to search for."
                                               class="search_input form-text" autocomplete="off" type="text"
                                               id="edit-search-block-form--2" name="search_block_form" value=""
                                               size="15" maxlength="128"/>
                                    </div>
                                    <div class="form-actions form-wrapper" id="edit-actions"><input
                                            class="search_submit form-submit" type="submit" id="edit-submit" name="op"
                                            value="Go"/></div>
                                    <input type="hidden" name="form_build_id"
                                           value="form-pSQDEesPY3AUW39vtsQoFJxvEQ753SIZYXQ4bf8JNN8"/>
                                    <input type="hidden" name="form_id" value="search_block_form"/>
                                </div>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
            <div class="utility_nav nav_hover nav_button_hover">
                <button class="utility_nav_button">Utilities</button>
                <nav class="utility_nav_links">
                    <a class="utility_nav_link" href="https://my.stevens.edu" style="color:black">myStevens</a>
                </nav>
            </div>
            <nav class="primary_nav">
                <ul class="menu">
                    <div class="primary_nav_item nav_hover"><a class="primary_nav_link" href="https://ideas-web-engine.appspot.com">Learn</a></button>
                        <div class="primary_nav_children"><a class="primary_nav_child_link"
                                                             href="https://ideas-web-engine.appspot.com">Design Spine
                            Admissions</a><a class="primary_nav_child_link" href="https://ideas-web-engine.appspot.com">Mechanical Hardware</a><a class="primary_nav_child_link" href="https://ideas-web-engine.appspot.com">Electronic Hardware</a><a class="primary_nav_child_link"
                                                  href="https://ideas-web-engine.appspot.com">Mechatronics</a><a
                                class="primary_nav_child_link" href="https://ideas-web-engine.appspot.com">No-Code/Low-Code Programming</a></div>
                    </div>
                    <div class="primary_nav_item nav_hover"><a class="primary_nav_link" href="http://ideas-web-engine.appspot.com/">Do</a>
                        <div class="primary_nav_children"><a class="primary_nav_child_link"
                                                             href="http://ideas-web-engine.appspot.com/">Machine Shop Training
                            Studies</a><a class="primary_nav_child_link" href="http://ideas-web-engine.appspot.com/">Proof Lab Job Requests
                            Studies</a><a class="primary_nav_child_link" href="http://ideas-web-engine.appspot.com/">3-D Printer Loaner Program
                            Schools</a><a class="primary_nav_child_link" href="http://ideas-web-engine.appspot.com/">IDEAS Workshops</a>
                        </div>
                    </div>
                    <div class="primary_nav_item nav_hover"><a class="primary_nav_link active two_lines"
                                                               href="http://ideas-web-engine.appspot.com"/>Pitch</a>
                        <div class="primary_nav_children"><a class="primary_nav_child_link"
                                                             href="/research-entrepreneurship/research-centers-labs">OIE Office
                                                             <a class="primary_nav_child_link"
                                                 href="/research-entrepreneurship/core-research-areas">SVC</a><a class="primary_nav_child_link"
                                        href="http://ideas-web-engine.appspot.com/">Expo Pitches</a><a class="primary_nav_child_link"
                                       href="http://ideas-web-engine.appspot.com/">Pitch your idea </a></div>
                    </div>
                    <div class="primary_nav_item nav_hover"><a class="primary_nav_link" href="http://ideas-web-engine.appspot.com/">About
                      </a>
                        <div class="primary_nav_children"><a class="primary_nav_child_link"
                                                             href="http://ideas-web-engine.appspot.com/">​IDEAS PROGRAM </a><a
                                class="primary_nav_child_link" href="http://ideas-web-engine.appspot.com/">Proof Lab</a><a class="primary_nav_child_link"
                                               href="http://ideas-web-engine.appspot.com/">Students Venture Center </a></div>
                    </div>
                </ul>
            </nav>
            <script async="async" src="https://gradadmissions.stevens.edu/ping">/**/</script>
        </div>

        <button class="mobile_navigation_handle js-mobile_handle">Navigation &amp; Search<span
                class="mobile_navigation_close">Close</span></button>
</header>
<center> <H1>
    Innovation, Design and Entrepreneurship (IDEaS) Program <BR> PROtotype Object Fabrication (PROOF) Laboratory  </H1>
    <H2> Carnegie 1st Floor, Stevens Institute of Technology<BR> Hoboken, NJ 07030 </H2></center> 
<center>
    <table width=95% id="table-3"> 
    <tr>
    <td width =70% align="center" style="vertical-align:middle" ></td> </tr>
    <tr> <td width =30% valign="top"> <h2> Useful Links </h2>
    <ul>
    <li> <A Href="/assets/instructions.pdf" style="color:red"> Job Submission and Delivery Process </A> </li>
    <li> <A Href="/assets/prooflab-machines.pdf" style="color:red"> Printers in the lab </A> </li>
    <li> Material Property Datasheets</li>
    <ul>
    <li><A Href="/assets/PJ-full-pallette.pdf" style="color:red"> Objet Full Pallette </A> </li>
    <li><A Href="/assets/polyjet_materials_data.pdf" style="color:red"> Polyjet Materials </A> </li>
    <li><A Href="/assets/digital-materials.pdf" style="color:red"> Objet Digital Materials </A> </li>
    <li><A Href="/assets/absplus.pdf" style="color:red"> Mojo/U-Print/Dimension (FDM) ABS+ </A> </li>
    <li><A Href="/assets/makerbot-pla-abs.pdf" style="color:red"> Makerbot PLA and ABS </A> </li>
    <li><A Href="http://www.stratasys.com/materials/material-safety-data-sheets" style="color:red"> MSDS for all Stratasys Materials </A> </li>
    </ul>
    <li> Reduce the cost of materials with appropriate <A HREF="/assets/infill.jpg"> infill. </A>
    <li> Cost guide for lab printers:
         <ul>
         <li> Setup cost (minimum charge) : $5 +
         <li> <A href="https://store.makerbot.com/replicator2.html" style="color:blue" >  Makerbot </A>: $2 per in^3 </li>
         <li> <A href="http://www.stratasys.com/3d-printers/idea-series/mojo" style="color:blue" > Mojo </A> |
          <A href="http://www.stratasys.com/3d-printers/design-series/dimension-1200es" style="color:blue" > Dimension </A>|
          <A href="http://www.stratasys.com/3d-printers/idea-series/uprint-se" style="color:blue" > U Print </A> : $6 per in^3   </li>
         <li> <A href="http://www.stratasys.com/3d-printers/production-series/connex3-systems" style="color:blue" >  Objet Connex350</A>: $15 per in^3  </li>
         </ul>
         <li> <A href="http://lazarsoft.info/objstl/#" style="color:"blue"> STL File Viewer </A> </li>
         <li> <A href="http://gcode.ws/" style="color:"blue"> G-Code Viewer  </A> </li>
         <li> <A href="http://www.greentoken.de/onlineconv/" style="color:"blue"> Convert File Format </A> </li>
         <li> <A Href="http://www.shapeways.com/tutorials/easy-3d-modeling-for-3d-printing-tutorial-for-beginners" style="color:red"> Guide to 3D Printing </A>  </li>
         <li> <A Href="http://www.3dpartprice.com/" style="color:red"> Estimate rough cost here </A> <BR> <B> Guide only and not an actual quote </B>   </li>
         <li> So we can't print what you want? <a href="https://www.3dhubs.com/"> Try here. </A>
    </ul>
    <p align="left">
    <A HREF="http://proof-lab-jobrequests.appspot.com" style="color:blue"> Login Page  </A> </P>
    <p align="left">
    <A HREF="http://proof-lab-jobrequests.appspot.com/admin" style="color:blue" > Admin Access  </A> </P>
    </td>
    <td width = 70%>
"""

FOOTER_STRING = """ 
</td> </tr> </table> </center>
<div class="region region-mobile-navigation">
    <div class="mobile_navigation js-mobile_navigation" aria-hidden="true" data-navigation-handle=".js-mobile_handle" data-navigation-content=".js-navigation_push" data-navigation-options='{"gravity":"right","labels":{"open":"Menu","closed":"Menu"},"type":"overlay"}'>
  <div class="mobile_navigation_container">
    <nav class="mobile_primary_nav">
            <div class="mobile_primary_nav_item">
        <a href="/about-stevens" class="mobile_primary_nav_link js-mobile_target_1">Learn    <span class="js-swap" data-swap-target=".js-mobile_target_1">Expand</span>
        </a>
                <div class="mobile_primary_nav_children js-mobile_target_1">
                    <a href="/about-stevens/mission" class="mobile_primary_nav_child_link">Design Spine </a>
                    <a href="/about-stevens/stevens-history" class="mobile_primary_nav_child_link">Mechanical Hardware> </a>
                    <a href="/about-stevens/facts-statistics" class="mobile_primary_nav_child_link"> Electronic Hardware </a>
                    <a href="/about-stevens/rankings-and-recognition" class="mobile_primary_nav_child_link">Mechatronics </a>
                    <a href="/about-stevens/leadership" class="mobile_primary_nav_child_link">No code/Low-code Programming </a>

                  </div>
              </div>
            <div class="mobile_primary_nav_item">
        <a href="/admissions" class="mobile_primary_nav_link js-mobile_target_2">Do    <span class="js-swap" data-swap-target=".js-mobile_target_2">Expand</span>
        </a>
                <div class="mobile_primary_nav_children js-mobile_target_2">
                    <a href="/admissions/undergraduate-admissions" class="mobile_primary_nav_child_link">Machine Shop Training </a>
                    <a href="/admissions/graduate-admissions" class="mobile_primary_nav_child_link">Proof Lab Job Requests</a>
                    <a href="/admissions/stevens-veterans-office" class="mobile_primary_nav_child_link">3D Printer Loaner Program</a>
                    <a href="/admissions/pre-college-programs" class="mobile_primary_nav_child_link">IDEAS Workshops </a> </div>
              </div>
            <div class="mobile_primary_nav_item">
        <a href="/academics" class="mobile_primary_nav_link js-mobile_target_3">Pitch    <span class="js-swap" data-swap-target=".js-mobile_target_3">Expand</span>
        </a>
                <div class="mobile_primary_nav_children js-mobile_target_3">
                    <a href="/academics/undergraduate-studies" class="mobile_primary_nav_child_link">OIE Office </a>
                    <a href="/academics/graduate-studies" class="mobile_primary_nav_child_link">SVC </a>
                    <a href="/academics/colleges-schools" class="mobile_primary_nav_child_link">Expo Pitches </a>
                    <a href="/academics/online-programs" class="mobile_primary_nav_child_link">Pitch your idea </a></div>
              </div>
            <div class="mobile_primary_nav_item">
        <a href="/research-entrepreneurship" class="mobile_primary_nav_link js-mobile_target_4">About    <span class="js-swap" data-swap-target=".js-mobile_target_4">Expand</span>
        </a>
                <div class="mobile_primary_nav_children js-mobile_target_4">
                    <a href="/research-entrepreneurship/research-centers-labs" class="mobile_primary_nav_child_link">IDEAS Program </a>
                    <a href="/research-entrepreneurship/core-research-areas" class="mobile_primary_nav_child_link">Proof LAB </a>
                    <a href="/research-entrepreneurship/annual-innovation-expo" class="mobile_primary_nav_child_link">Stevens Venture Center </a>
                    
                  </div>
              </div>
            <div class="mobile_primary_nav_item">
        <a href="/campus-life" class="mobile_primary_nav_link js-mobile_target_5"> 
        
              </div>
          </nav>

    <div class="mobile_search_module">
      <form class="search_form" action="/research-entrepreneurship/innovation-entrepreneurship/ideas-proof-lab" method="post" id="search-block-form--2" accept-charset="UTF-8"><div><div class="container-inline">
      <h2 class="element-invisible">Search form</h2>
    <div class="form-item form-type-textfield form-item-search-block-form">
  <label class="element-invisible" for="edit-search-block-form--4">Search </label>
 <input title="Enter the terms you wish to search for." class="search_input form-text" autocomplete="off" type="text" id="edit-search-block-form--4" name="search_block_form" value="" size="15" maxlength="128" />
</div>
<div class="form-actions form-wrapper" id="edit-actions--2"><input class="search_submit form-submit" type="submit" id="edit-submit--2" name="op" value="Go" /></div><input type="hidden" name="form_build_id" value="form-EGlKbjHjwVwJr_bJZgoBVPadsYnrnnSW4Vt9kgrnWzU" />
<input type="hidden" name="form_id" value="search_block_form" />
</div>
</div></form>   </div>
    </div>
  </div>
</div>
  </div>
  <!-- Modernizer -->
    <script src="https://www.stevens.edu/sites/all/themes/stevens/js/modernizr.js?t=201701121240"></script>

    <script type="text/javascript" src="https://www.stevens.edu/sites/stevens_edu/files/js/js_gPM6NXOQjN2XM2JWQGfy07nKmcdDFrL289YA7h80ySs.js"></script>
<script type="text/javascript" src="https://www.stevens.edu/sites/stevens_edu/files/js/js_oZD9-WvfiElJ5KPavqu9ZAQiZcfWlzNCzxFHpedR9dI.js"></script>
<script type="text/javascript" src="https://www.stevens.edu/sites/stevens_edu/files/js/js_oDrIg1Ksill5Q_HZSlyO34-DtWPW2FpZMrtlmr55Cuc.js"></script>
<script type="text/javascript" src="https://www.stevens.edu/sites/stevens_edu/files/js/js_gPqjYq7fqdMzw8-29XWQIVoDSWTmZCGy9OqaHppNxuQ.js"></script>
<script type="text/javascript">
<!--//--><![CDATA[//><!--
(function(i,s,o,g,r,a,m){i["GoogleAnalyticsObject"]=r;i[r]=i[r]||function(){(i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)})(window,document,"script","//www.google-analytics.com/analytics.js","ga");ga("create", "UA-4037868-9", {"cookieDomain":"auto"});ga("set", "anonymizeIp", true);ga("send", "pageview");
//--><!]]>
</script>
<script type="text/javascript">
<!--//--><![CDATA[//><!--
jQuery.extend(Drupal.settings, {"basePath":"\/","pathPrefix":"","ajaxPageState":{"theme":"stevens","theme_token":"Z9aNnoQPhugbmxsgwF60Snk_aLEyQyJRQFbmZZtiUyA","js":{"sites\/all\/modules\/contrib\/jquery_update\/replace\/jquery\/1.10\/jquery.min.js":1,"misc\/jquery.once.js":1,"misc\/drupal.js":1,"sites\/all\/modules\/contrib\/jquery_update\/replace\/ui\/ui\/minified\/jquery.ui.core.min.js":1,"sites\/all\/modules\/contrib\/jquery_update\/replace\/ui\/ui\/minified\/jquery.ui.widget.min.js":1,"sites\/all\/modules\/contrib\/jquery_update\/replace\/ui\/ui\/minified\/jquery.ui.position.min.js":1,"sites\/all\/modules\/contrib\/jquery_update\/replace\/ui\/ui\/minified\/jquery.ui.menu.min.js":1,"sites\/all\/modules\/contrib\/jquery_update\/replace\/ui\/ui\/minified\/jquery.ui.autocomplete.min.js":1,"sites\/all\/modules\/contrib\/google_cse\/google_cse.js":1,"sites\/all\/modules\/contrib\/gss\/scripts\/autocomplete.js":1,"sites\/all\/modules\/contrib\/google_analytics\/googleanalytics.js":1,"1":1}},"googleCSE":{"cx":"001121190494222698426:1_dk_pysrr0","language":"","resultsWidth":600,"domain":"www.google.com"},"gss":{"key":""},"googleanalytics":{"trackOutbound":1,"trackMailto":1,"trackDownload":1,"trackDownloadExtensions":"7z|aac|arc|arj|asf|asx|avi|bin|csv|doc(x|m)?|dot(x|m)?|exe|flv|gif|gz|gzip|hqx|jar|jpe?g|js|mp(2|3|4|e?g)|mov(ie)?|msi|msp|pdf|phps|png|ppt(x|m)?|pot(x|m)?|pps(x|m)?|ppam|sld(x|m)?|thmx|qtm?|ra(m|r)?|sea|sit|tar|tgz|torrent|txt|wav|wma|wmv|wpd|xls(x|m|b)?|xlt(x|m)|xlam|xml|z|zip"},"urlIsAjaxTrusted":{"\/research-entrepreneurship\/innovation-entrepreneurship\/ideas-proof-lab":true}});
//--><!]]>
</script>

    <!--[if IE 8]>
      <script>var IE8 = true;</script>
      <script src="/sites/all/themes/stevens/js/site-ie8.js?t=201701121240"></script>
    <![endif]-->
    <!--[if IE 9]>
      <script>var IE9 = true;</script>
      <script src="/sites/all/themes/stevens/js/site-ie9.js?t=201701121240"></script>
    <![endif]-->

    <!-- Compiled JS -->
    <script>$ = jQuery;</script>
    <script src="https://www.stevens.edu/sites/all/themes/stevens/js/site.js?t=201701121240"></script>
    <script type="text/javascript">
<!--//--><![CDATA[//><!--
setTimeout(function(){var a=document.createElement("script");
var b=document.getElementsByTagName('script')[0];
a.src=document.location.protocol+"//script.crazyegg.com/pages/scripts/0049/8919.js?"+Math.floor(new Date().getTime()/3600000);
a.async=true;a.type="text/javascript";b.parentNode.insertBefore(a,b)}, 1);
//--><!]]>
</script>
  </body>

</body>
</html>"""

mainformheadhtml = """
<form id="form" class="form" name="form" method="post" action="/login" enctype="application/x-www-form-urlencoded"  accept-charset="UTF-8">
    <p>  <b> Job Submissions </b>
    </p><div class="content">
        <div class="intro"><p>This form is for submitting prototyping jobs for <strong>Stevens Institute of Technology</p>
        <FONT COLOR=RED> <B> Typical Print Cycle:  ~5 business days after advisor approval </B>
        <P>
        </FONT></FONT> </div>
        <div id="section0" >
        </div> """


identifyformfields = """
        <h2 class="section">Identify Yourself</h2>
        <div id="section1" >
            <div class="field"><label for="Name">Name</label><input type="text" id="uname" name="uname" required></div>
            <div class="field"><label for="Access code">Access Code (No Code? Leave Blank) </label><input type="password" id="ucode" name="ucode" maxlength="9"></div>
            <div class="field"><label for="uemail">Email address (<b> user id only </b>; <FONT Color="red"> @stevens.edu is automatically added </FONT>)</label><input type="text" id="uemail" name="uemail" size="25" required></div>
            <div class="field"><label for="GetAccessCode">Login OR Get Access Code (Fill Name, Email and leave the access code blank) </label><input type="submit" id="uGetAccessCode" name="GetAccessCode" class="button" value="Login / Get Code"></div>
        </div> """


jobrequestformfields = """
    <h2 class="section"><p> Project  Description (Fill-in for new job submissions only) </p></h2>
    <div id="section2" >
    <div class="field"><label for="ProjectName">Project Name</label><input type="text" id="uproject" name="uproject" size="15" required></div>
    <div class="field"><label for="Course Name Number">Course Number and Section</label><input type="text" id="ucourse" name="ucourse" size="25" placeholder="ME 423 X2"></div>
    <div class="field"><label for="AdvisorsName">Project Advisor's Name</label><input type="text" id="uadvisor" name="uadvisor" placeholder="Prof. " required></div>
    <div class="field"><label for="Advisors Emailstevenseduisautomaticallyadded">Advisor's Email (@stevens.edu is automatically added)</label><input type="text" id="uadvisoremail" name="uadvisoremail" required></div>
    </div>
    <h2 class="section"><p> Job Description (Fill-in for new job submissions only) </p></h2>
    <div id="section3" >
    <label for="unitsmm"> <FONT color="red"> <B> Binary STL files only - Length units are interpreted as mm - Make sure you save the stl in mm. </B> </FONT> </label>
    <input type="file" id="file" name="file" required />
    <div class="field"><label for="Materialtobeusedleaveblankifthelabcanselect">Material to be used (leave blank if the lab can select)</label><input type="text" id="umaterial" name="umaterial"></div>
    <div class="field"><label for="partdescription"> Write a short note on the intended use and indicate any stiffness, strength and dimensional requirements." </label>
    <textarea type="textarea" class="textarea" id="udescription" name="udescription">
        </textarea>
    </div>
    <div class="field"><label for="Process Form">Submit (May take a while as the app computes volumes and cost)</label><input type="submit" id="ProcessForm" name="Process Form"></div>
    </div> """

formtail = """
    </div>
</form>
"""

ALLOWED_MIMETYPES = ['application/stl','application/sldprt' ]

#Session Handling class, gets the store, dispatches the request
class BaseSessionHandler(webapp2.RequestHandler):
    def dispatch(self):
        # Get a session store for this request.
        self.session_store = sessions.get_store(request=self.request)
        
        try:
            # Dispatch the request.
            webapp2.RequestHandler.dispatch(self)
        finally:
            # Save all sessions.
            self.session_store.save_sessions(self.response)
    @webapp2.cached_property
    def session(self):
        # Returns a session using the default cookie key.
        return self.session_store.get_session()
#End of BaseSessionHandler Class

#def SendGridMail():
#    # make a secure connection to SendGrid
#    sg = SendGridClient('<sendgrid_username>', '<sendgrid_password>', secure=True)
#
#    # make a message object
#    message = Mail()
#    message.set_subject('message subject')
#    message.set_html('<strong>HTML message body</strong>')
#    message.set_text('plaintext message body')
#    message.set_from('from@example.com')
## add a recipient
#    message.add_to('John Doe <someone@example.com>')
## use the Web API to send your message
#    sg.send(message)

def database_key(database_name=DEFAULT_DATABASE_NAME):
    """Constructs a Datastore key ."""
    return ndb.Key('ProofLabJobs', database_name)

#login and user access code management

def KeyGenerator(size=9, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

class ResendHandler(webapp2.RequestHandler):
    def get(self, resource1):
        uemail = str(urllib2.unquote(resource1))
        qry = UserDB.query(UserDB.email == uemail)
        if qry.iter(keys_only=True).has_next():
            userrecord = qry.fetch(1)
            accesskey= userrecord[0].accesscode
            eresponse=EmailCodes(uemail,accesskey)
            self.response.out.write(HEADER_STRING)
            self.response.out.write("""<center> <H2> %s <BR>
                <A HREF='/'> Back to login page </A> </H2></CENTER>"""
                                    % eresponse)
            self.response.out.write(FOOTER_STRING)

def EmailCodes(uemail,accesscode):
    subjectstr = "PROOF LAB Job Submission Access"
    message = mail.EmailMessage(sender='Proof Lab Job Requests <proof-lab-jobrequests@appspot.gserviceaccount.com>', subject = subjectstr)
    message.to = uemail + '@stevens.edu'
    message.body = 'Dear ' + uemail +', \n Your access Code is:  ' +accesscode
    message.body = message.body+ '\n Please return to the app to sign in. \n This is an auto-generated message. Do not reply to this address.'
    #print message.body
    #print message.to
    try:
        message.send()
    except apiproxy_errors.OverQuotaError, message:
    #    logging.error(message)
        return 'Sorry! Daily Email Quota Exceeded. Process is moving forward.'
    return 'Access Code E-Mail has been Queued to: '+ uemail + "@stevens.edu"

class RemindAdvisor(webapp2.RequestHandler):
    def get(self,resource1,resource2):
        jobid = str(urllib2.unquote(resource1))
        advemail = str(urllib2.unquote(resource2))
        EmailAdvisor(jobid)
        self.response.out.write(HEADER_STRING)
        self.response.out.write("""<center> <H2> Advisor (<FONT COLOR=RED> %s@stevens.edu </FONT>) has been emailed again.  <P>
             Contact your advisor about job authorization. <P>  If there is an error in the advisor's email
             address, withdraw the job and resubmit it again. <P> Ask the advisor to check junk, bulk and spam folders
             as emails with links may go to these folders based on spam settings. <P>
                <A HREF='/'> Back to the login page </A> </H2></CENTER>""" % advemail)
        self.response.out.write(FOOTER_STRING)


class WidthdrawHandler(webapp2.RequestHandler):
    def get(self,resource1):
        jobid = str(urllib2.unquote(resource1))
        thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
        thisjob.state = 7
        thisjob.put()
        self.response.out.write(HEADER_STRING)
        self.response.out.write("""<center> <H2> Your job request has been withdrawn.  <P>
            If this is in error, resubmit the job again <P>
            <A HREF='/'> Back to the login page </A> </H2></CENTER>""" )
        self.response.out.write(FOOTER_STRING)


def EmailAdvisor(jobid):
    thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
    uemail = thisjob.useremail
    uid = thisjob.userkey
    thisuser = UserDB.get_by_id(int(uid),parent=database_key(DEFAULT_DATABASE_NAME))
    uname = thisuser.name
    partvolume = thisjob.partvolume
    bbox0 = float(thisjob.boundingbox.split("'")[1])
    bbox1 = float(thisjob.boundingbox.split("'")[3])
    bbox2 = float(thisjob.boundingbox.split("'")[5])
    bbox3 = float(thisjob.boundingbox.split("'")[7])
    bbox4 = float(thisjob.boundingbox.split("'")[9])
    bbox5 = float(thisjob.boundingbox.split("'")[11])
    bboxvolume=(bbox1-bbox0)*(bbox3-bbox2)*(bbox5-bbox4)
    aemail  = thisjob.advisoremail
    aname = thisjob.advisorname
    stlblobquoted = urllib2.quote(thisjob.stlblobkey)
    viewurl = 'http://proof-lab-jobrequests.appspot.com/viewer/' + stlblobquoted
    subjectstr = 'Job approval for: '+ uname + ', Job # ' + thisjob.jobidcode
    message = mail.EmailMessage(sender='Proof Lab Job Requests <proof-lab-jobrequests@appspot.gserviceaccount.com>', subject = subjectstr)
    message.to = aemail + '@stevens.edu'
    #message.to = 'kishore.stevens@gmail.com'
    costmaker = int(float(partvolume)*costlist[0]) + SETUPCOST
    costmojo = int(float(partvolume)*costlist[3])  + SETUPCOST
    costconnex = int(float(bboxvolume)*costlist[7])+ SETUPCOST
    messagebodystr = ("""
Dear %s,
Your student %s has initiated a 3D print job at the PROOF Lab.
The uploaded file has been analyzed and the following budgetary cost estimate
has been automatically generated. The actual cost will vary based
on the support material used and post processing time required.
--------------------------------------------------------------------
        
Geometry::
  Part Volume: %s cm^3
  Bounding Box[x_min,x_max,y_min,y_max,z_min,z_max] in cm:
    %s
  Note: If part volume is reported rounded to 0, check the units of the
  submitted stl files.
        
Costs based on machine requested::
Makerbot (PLA/ABS)                  :  $ %s
Mojo/Dimension/Uprint (ABS+)        :  $ %s
Objet Connex - 350                  :  $ %s
        
If you have questions, please contact the student at : %s@stevens.edu
        
Please add proof-lab-jobrequests@appspot.gserviceaccount.com to your contact
list to ensure robust delivery of these email messages.
        """  % (aname,uname,partvolume,thisjob.boundingbox, str(costmaker),str(costmojo), str(costconnex),uemail))
    message.body =  messagebodystr
#    print message.body
# Change this back to 1 after the email issues are fixed.
    thisjob.state = 2
    thisjob.put()
    try:
        message.send()
# 0. Processing Estimate 1. Waiting Advisor 2. Authorized; 3. Revisions 4. Scheduled 5. Delivered 6. Closed
    except apiproxy_errors.OverQuotaError, message:
        #        logging.error(message)
        # perhaps we should try the sendgrid api - have username (mechware) and password- check keypass
        return 'Sorry! Daily Email Quota Exceeded. However, the process is moving forward'
    return 'Authorization Email has been Queued: '+ uemail + "@stevens.edu"
###
#If you wish to approve, please click the link below :
#    http://proof-lab-jobrequests.appspot.com/advisorok/%s
#  str(thisjob.jobidcode)
#    Lab Website: http://proof-lab-jobrequests.appspot.com

class AdvisorHandler(webapp2.RequestHandler):
    def get(self,resource1):
        jobid = str(urllib2.unquote(resource1))
        qry = LabJobsDB.query(LabJobsDB.jobidcode == jobid)
        self.response.out.write(HEADER_STRING)
        if qry.iter(keys_only=True).has_next():
            userrecord = qry.fetch(1)
            thisjob = userrecord[0]
# 0. Processing Estimate 1. Waiting Advisor 2. Authorized; 3. Revisions 4. Scheduled 5. Delivered 6. Closed
            thisjob.state = 2
            thisjob.authorized= datetime.now()
            thisjob.put()
            self.response.out.write(""" <H1> PROOF LAB:: Job Authorization  <p>
                 Jobid:  <FONT COLOR=red> %s </FONT> submitted by <FONT COLOR=red> %s </FONT>
                 has been approved by <FONT COLOR=red> %s </FONT>. <P>
                This job will now be reviewed and moved to the print queue. </FONT> </H1>""" % (thisjob.jobidcode,thisjob.useremail,thisjob.advisorname))
        else:
            self.response.out.write(""" <H1> PROOF LAB </H1> <p> Job not found in the database. As""")
        self.response.out.write(FOOTER_STRING)


def consultform(sessionid):
    html2 = """
        <form action="ProcessConsult" method="post">
        <label>
        <span>Part Identifier:</span>
        <input id="pname" type="text" name="pname" size=30 placeholder="Part Number"  required= "required"  />
        </label>
        <label>
        <span>Upload Stl part file:</span>
        <input type="file" name="pfile" required/>
        </label>
        <label>
        <span>&nbsp;</span>
        <input type="submit" class="button" value="Logout" />
        </label>
        </form>
        """
    return html2

class SignupHandler(webapp2.RequestHandler):
    def post(self):
        uname=self.request.get('uname')
        uemail=self.request.get('uemail')
        ucode=self.request.get('ucode')
        uterms = self.request.get('uterms')
        if '@' in uemail:
            emailid = uemail.split('@')
            uemail  = emailid[0]
        self.response.out.write(HEADER_STRING)
        # Search if email exists in the user base if not generate code and send
        uterms  = "consented"
        if(uterms != "consented"):
            # someone using safari or other browser to skip agreement to terms and conditions
            self.response.out.write("""<center>
                <h1>Proof Lab Job Requests </h1>
                <h2> You must consent to rules and regulations of PROOF Lab. </h2>
                <P> <A HREF='/'> Please revisit the login page and agree to the terms </A></P>
                """)
            return
        qry = UserDB.query(UserDB.email == uemail)
        if qry.iter(keys_only=True).has_next():
            userrecord = qry.fetch(1)
            # If email exists and code does not match, email code again
            accesscode = userrecord[0].accesscode
            if(accesscode == ucode):
                # Check if reservation exists
                # Eligibility - Expired Reservation / 72 hours before the reservation?
                uid = userrecord[0].key.id()
                # check if any jobs exist  - Each user can only have 2 pending jobs; each advisor only 5 jobs.
                upload_url = blobstore.create_upload_url('/upload')
                self.response.write("""    <form id="form" class="form" name="form2" method="post" action="%s" enctype="multipart/form-data">
                <h1> PROOF LAB </h1> <h2> Prototype Object Fabrication Laboratory </h2> <p>  <b> Job Submissions </b>
                </p><div class="content">
                <div class="intro"><p>This form is for submitting prototyping jobs for <strong>Stevens Institute of Technology</strong> students only.&nbsp;</p>
                <FONT COLOR=RED> <B> Current Wait Time: ~5 business days after advisor approval </B> <P>
                NOW ACCEPTING ONLY SENIOR DESIGN JOBS - No other projects on OBJET or Mojos. </FONT>
                </div>
                <div id="section0" >
                </div>
                    """ % upload_url)
                self.response.write("""
                    <input id="uemail" type="hidden" name="uemail" value= "%s" />
                    """ % uemail )
                self.response.write(UserJobsList(uemail))
                #self.response.write("""<H2> System is currently under maintenance. <P> Please try again on 4/11/2016 </H2>""")
                self.response.write(jobrequestformfields)
                self.response.write(formtail)
                self.response.out.write(FOOTER_STRING)
                return
            else:
                self.response.out.write(""" <CENTER> <H2> Incorrect Access Code. Please check your email <BR> """)
                self.response.out.write("""
                    <A HREF=/resend/%s>
                    Click here to resend code. </A>  <BR> </H2> </CENTER> """ % uemail)
                self.response.out.write(FOOTER_STRING)
                return
        else:
            # Create the user and email
            newkey = KeyGenerator()
            dnd = UserDB(parent=database_key(DEFAULT_DATABASE_NAME),
                         email=uemail, name=uname,accesscode=newkey)
            dnd.put()
            self.response.out.write("""<center> <H3> A new access key has been created. Please check  %s@stevens.edu
                             to get the code.    """ % uemail)
            eresponse=EmailCodes(uemail,newkey)
            self.response.out.write("""</H3>  </center>""")
                             # New code created or code did not match. Code was sent to your addresss.
            self.response.out.write(FOOTER_STRING)

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler,webapp2.RequestHandler):
    def post(self):
        uemail=self.request.get('uemail')
        self.response.out.write(HEADER_STRING)
        qry = UserDB.query(UserDB.email == uemail)
        if qry.iter(keys_only=True).has_next():
            userrecord = qry.fetch(1)
            uid = userrecord[0].key.id()
            username = userrecord[0].name
        else:
            self.response.out.write(""" <CENTER> <H2> User not found in DB <BR> """)
            self.response.out.write("""
                    <A HREF="/"> Relogin, Please </A>""" )
            return
        ufile=self.request.get('file')
        #print ufile
        ucourse=self.request.get('ucourse')
        uproject=self.request.get('uproject')
        ucourse=self.request.get('ucourse')
        uadvisor=self.request.get('uadvisor')
        uadvisoremail=self.request.get('uadvisoremail')
        udescription =self.request.get('udescription')
        if '@' in uadvisoremail:
            emailid = uadvisoremail.split('@')
            uadvisoremail  = emailid[0]
#        upartvolume=self.request.get('upartvolume')
#        uboundingbox=self.request.get('uBoundingBox')
        umaterial = "PLA"
        umaterial=self.request.get('umaterial')
        usupportmaterial = "0"
        usupportmaterial=self.request.get('usupportmaterial')
        timestampnow = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp2 =datetime.now().strftime("%Y-%m-%d-%H_%M_%S")
    # Upload the file into a blob
        upload_files = self.get_uploads('file')  # 'file' is file upload field in the form
        if(len(upload_files) == 0 ):
            self.response.out.write("<h2> ERROR:: Upload file had no data </h2>")
            self.response.out.write(FOOTER_STRING)
            return
        blob_info = upload_files[0]

        if not blob_info.filename.lower().endswith(".stl"):
            self.response.out.write("<h2> Sorry!!! ERROR:: ONLY .stl FILES ARE ACCEPTED</h2>")
            self.response.out.write(FOOTER_STRING)
            return
        
        blob_reader = blobstore.BlobReader(blob_info)
        #attfile  =  uemail +"_"+timestamp2+ "_"+ blob_info.filename
        if(blob_info.size > 20971520*4):
            self.response.out.write('<br> File Rejected. ERROR: FILE SIZE IS ABOVE LIMIT (80 MB). Please Resubmit <BR>')
            self.response.out.write(FOOTER_STRING)
            return
        self.response.out.write(' <H2> Job Received from: %s  at UTC %s  <BR>' % (username, timestampnow))
        self.response.out.write(' <File received was: %s type: %s </H2>' % (blob_info.filename,blob_info.content_type))
        self.response.out.write(""" Cost estimates will be available in a few minutes. <P> An email will be sent out to your advisor (cc'ed to you) with the part volume and estimated costs. <P> Use brower back button and return to the login page and refresh/reload it. <BR>  - <A HREF="http://proof-lab-jobrequests.appspot.com/" onClick="history.back();return false;">Click here to go back  </A> and do not forget to refresh/reload. """)
        
#       self.response.out.write(' File has been written to Google Drive %s <br>' % attfile)
        uengineer = str("bgebre")
        upartvolume = str("-9999")
        uboundingbox = str ("-9999,9999,-9999,9999,-9999,9999")
        ujobidcode = KeyGenerator()
        dnd = LabJobsDB(parent=database_key(DEFAULT_DATABASE_NAME),
             useremail=uemail,userkey= str(uid),advisorname=uadvisor, advisoremail=uadvisoremail,
             projectname=uproject,sdsection=ucourse,boundingbox=uboundingbox, filename=blob_info.filename,
                partvolume=upartvolume, supportvolume = usupportmaterial,state=0,stlblobkey=str(blob_info.key()),
                        machineassigned="none", partmaterial = umaterial,description = udescription,
                        engineer = uengineer,jobidcode=ujobidcode)
        dnd.put()
        taskqueue.add(url='/computevolume',params={'jobid':str(dnd.key.id())})
        self.response.out.write(FOOTER_STRING)

class ComputeVolume(webapp2.RequestHandler):
    def post(self):
        jobid = self.request.get('jobid')
        if jobid is None:
            return
        thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
        if thisjob is None:
            return
        mySTLUtils = STLUtils()
        upartvolume = str(int(mySTLUtils.calculateVolume(str(thisjob.stlblobkey),"cm")))
#        print "#3", upartvolume
        uboundingbox1 = mySTLUtils.boundingbox
        bboxvolume=(uboundingbox1[1]-uboundingbox1[0])*(uboundingbox1[3]-uboundingbox1[2])*(uboundingbox1[5]-uboundingbox1[4])
        uboundingbox = str(["{:.2f}".format(x / 10) for x in uboundingbox1])
        thisjob.partvolume = upartvolume
        thisjob.boundingbox = uboundingbox
        # put this back to 1 to get the advisor back into the loop
        thisjob.state = 2
        thisjob.put()
        volpart = float(upartvolume)
        costmaker = str(int(volpart * costlist[0])+ SETUPCOST)
        costmojo = str(int(volpart * costlist[3])+ SETUPCOST)
        costconnex = str(int(bboxvolume *costlist[7])+ SETUPCOST)
        EmailAdvisor(jobid)



def UserJobsList(uemail):
    qry = LabJobsDB.query(LabJobsDB.useremail == uemail)
    if qry.iter().has_next():
        slots= qry.fetch()
        outhtml  = (""" <H2> Job Status List for: %s@stevens.edu </H2>  <table id="table-3"> <thead> <th> Job No. </th> <th> Created </th> <th> File View <BR> Opens Tab/Window </th> <th> Status </th> <th> Cost ($) <BR> Makerbot </th>
            <th> Cost ($) <BR> Mojo/Uprint/dimension </th>
            <th> Cost ($) <BR> Objet-Connex </th> </thead> <tbody> """ % uemail)
        jobcount = 0
        for slot in slots:
            jobcount = jobcount+1
            volpart = float(slot.partvolume)
            if volpart < 0 :
                costmaker  = "Estimate Pending: "
                costmojo  = " Check here in a few minutes"
                costconnex  = " ... "
            else:
                costmaker = str(int(volpart * costlist[0])+ SETUPCOST)
                costmojo = str(int(volpart * costlist[3])+ SETUPCOST)
                costconnex = str(int(volpart *costlist[7])+ SETUPCOST)
            outhtml = outhtml + (""" <tr> <td> %s </td> <td> %s </td>
                <td> %s <BR> <A href=/viewer/%s target="_blank"> Viewer </A> """ %
                            (str(jobcount),slot.created,slot.filename, slot.stlblobkey))
            if slot.state == 1 :
                outhtml = outhtml + ("""| <A href=/remindadvisor/%s/%s target="_blank"> Email Advisor Again </A> """ %
                                 (str(slot.key.id()),slot.advisoremail))
            if slot.state < 5:
                outhtml = outhtml + (""" | <A href=/withdraw/%s target="_blank"> Withdraw </A> </td> """
                                     % str(slot.key.id()))
            outhtml = outhtml + ("""  <td> %s </td>
                <td> %s </td>  <td> %s </td>  <td> %s </td> </tr> """ %
                    (statelist[slot.state],
                     costmaker,costmojo,costconnex))
        outhtml = outhtml + """</tbody> </table> <P>  """
    else:
        outhtml = """ <H2> Job Status List </H2> <P> No Jobs Requested </P> """
    return outhtml

class STLUtils:
    def resetVariables(self):
        #self.normals = []
        #self.points = []
        #self.triangles = []
        #self.bytecount = []
        #self.fb = [] # debug list
        self.boundingbox=[]
        self.numtri = 0
        # Calculate volume fo the 3D mesh using Tetrahedron volume
        # based on: http://stackoverflow.com/questions/1406029/how-to-calculate-the-volume-of-a-3d-mesh-object-the-surface-of-which-is-made-up
    def signedVolumeOfTriangle(self,p1, p2, p3):
        v321 = p3[0]*p2[1]*p1[2]
        v231 = p2[0]*p3[1]*p1[2]
        v312 = p3[0]*p1[1]*p2[2]
        v132 = p1[0]*p3[1]*p2[2]
        v213 = p2[0]*p1[1]*p3[2]
        v123 = p1[0]*p2[1]*p3[2]
        return (1.0/6.0)*(-v321 + v231 + v312 - v132 - v213 + v123)
    
    def unpack(self, sig, l):
        s = self.f.read(l)
        #self.fb.append(s)
        return struct.unpack(sig, s)
    
    def read_triangle(self):
        n  = self.unpack("<3f", 12)
        p1 = self.unpack("<3f", 12)
        p2 = self.unpack("<3f", 12)
        p3 = self.unpack("<3f", 12)
        b  = self.unpack("<h", 2)
        self.boundingbox[0] = min(self.boundingbox[0],p1[0],p2[0],p3[0])
        self.boundingbox[1] = max(self.boundingbox[1],p1[0],p2[0],p3[0])
        self.boundingbox[2] = min(self.boundingbox[2],p1[1],p2[1],p3[1])
        self.boundingbox[3] = max(self.boundingbox[3],p1[1],p2[1],p3[1])
        self.boundingbox[4] = min(self.boundingbox[4],p1[2],p2[2],p3[2])
        self.boundingbox[5] = max(self.boundingbox[5],p1[2],p2[2],p3[2])
        #self.normals.append(n)
        #l = len(self.points)
        #self.points.append(p1)
        #self.points.append(p2)
        #self.points.append(p3)
        #self.triangles.append((l, l+1, l+2))
        #self.bytecount.append(b[0])
        return self.signedVolumeOfTriangle(p1,p2,p3)
    
    def read_triangle_ascii(self):
        p1 = [ 0.0, 0.0, 0.0]
        p2 = [ 0.0, 0.0, 0.0]
        p3 = [ 0.0, 0.0, 0.0]
        i=0
        for line in self.f:
            #print line
            part=line.split()
            if 'endsolid' in part:
                raise Exception('End of Triangles')
            #print str(part)
            if 'vertex' in part:
                if(i == 2):
                    p3[0] = float(part[1])
                    p3[1] = float(part[2])
                    p3[2] = float(part[3])
                    self.boundingbox[0] = min(self.boundingbox[0],p1[0],p2[0],p3[0])
                    self.boundingbox[1] = max(self.boundingbox[1],p1[0],p2[0],p3[0])
                    self.boundingbox[2] = min(self.boundingbox[2],p1[1],p2[1],p3[1])
                    self.boundingbox[3] = max(self.boundingbox[3],p1[1],p2[1],p3[1])
                    self.boundingbox[4] = min(self.boundingbox[4],p1[2],p2[2],p3[2])
                    self.boundingbox[5] = max(self.boundingbox[5],p1[2],p2[2],p3[2])
                    self.numtri +=1
                    return self.signedVolumeOfTriangle(p1,p2,p3)
                if(i == 1):
                    p2[0] = float(part[1])
                    p2[1] = float(part[2])
                    p2[2] = float(part[3])
                    i = 2
                if(i == 0):
                    p1[0] = float(part[1])
                    p1[1] = float(part[2])
                    p1[2] = float(part[3])
                    i = 1
        raise Exception('End of Triangles')
    
    def read_length(self):
        length = struct.unpack("@i", self.f.read(4))
        return length[0]
    
    def ISAscii(self):
        self.f.seek(0)
        firstsix = self.f.read(6)
        self.f.seek(0)
        if firstsix == "solid ":
            #print "FILE IS ASCII"
            # read the second line and look for the word facet
            try:
                firstline = self.f.readline()
                secondline = self.f.readline()
                thirdline = self.f.readline()
                if('facet' in secondline.lower()) or ('facet' in thirdline.lower()):
                    self.f.seek(0)
                    print "FILE IS ASCII"
                    return True
                else:
                    self.f.seek(0)
                    return False
            except Exception, e:
                    self.f.seek(0)
                    return False
            self.f.seek(0)
            return True
        else:
            #print "FILE IS Binary"
            self.f.seek(0)
            return False
    
    def read_header(self):
        self.f.seek(self.f.tell()+80)
    
    def cm3_To_inch3Transform(self, v):
        return v*0.0610237441
    
    def calculateWeight(self,volumeIn_cm):
        return volumeIn_cm*1.2
    
    def calculateVolume(self,blob_key,unit):
        self.resetVariables()
        self.boundingbox = [0.0,0.0,0.0,0.0,0.0,0.0]
        totalVolume = 0
        tricount = 0
        try:
            self.f = blobstore.BlobReader(blob_key)
            if not self.ISAscii() :
                self.read_header()
                l = self.read_length()
                #print "total triangles:",l
                try:
                    while True:
                        totalVolume +=self.read_triangle()
                except Exception, e:
                    pass
                    #print "#1", e, totalVolume
                    #print "End calculate triangles volume"
                    #print len(self.normals), len(self.points), len(self.triangles), l,
            else:
            #File is Ascii
                try:
                    while True:
                        totalVolume += self.read_triangle_ascii()
#                        tricount += 1
#                        if (tricount % 1000) == 0 :
#                            print tricount, totalVolume
                except Exception, e:
                    pass
                        #print e
                        #print "End calculate triangles volume"
                        #print len(self.normals), len(self.points), len(self.triangles), l,
            if unit=="cm":
                totalVolume = (totalVolume/1000)
                #print "Total volume:", totalVolume,"cm"
            else:
                totalVolume = self.cm3_To_inch3Transform(totalVolume/1000)
                    #print "Total volume:", totalVolume,"inch"
        except Exception, e:
            pass
        return totalVolume

# Calling it mySTLUtils.calculateVolume(sys.argv[1],"cm")


class JobUpdateHandler(webapp2.RequestHandler):
    def post(self):
        #print resource1, resource2, resource3
        if IsUserAdmin() :
            actionid=self.request.get('actionid')
            if(actionid == 'schedule') :
# Update the job id's state to scheduled
# update machine
# 0. Processing Estimate 1. Waiting Advisor 2. Authorized; 3. Revisions 4. Scheduled 5. Delivered 6. Closed
                jobid=self.request.get('jobid')
                machineid =self.request.get('umachine')
                materialid =self.request.get('umaterial')
                thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
                thisjob.state  = 4
                thisjob.machineassigned = machineid
                thisjob.partmaterial = materialid
                thisjob.scheduled = datetime.now()
                thisjob.put()
            if(actionid == 'review') :
        # Update the job id's state to scheduled
        # update machine
                adminuser = users.get_current_user()
                adminemail = adminuser.email()
                jobid=self.request.get('jobid')
                umessage =self.request.get('umessage')
                print umessage
                thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
                uemail = thisjob.useremail
                thisjob.state  = 3
                thisjob.reviewed = datetime.now()
                thisjob.put()
                subjectstr = 'Revisions Needed - Proof Lab Admin:'+ adminemail
                message = mail.EmailMessage(sender='Proof Lab Job Requests <proof-lab-jobrequests@appspot.gserviceaccount.com>', subject = subjectstr)
                message.to = uemail + '@stevens.edu'
                message.body = 'Dear Student,\n ** PLEASE DO NOT REPLY TO THIS EMAIL ** \n'
                message.body = message.body + 'RESPOND DIRECTLY TO: '+ adminemail
                message.body = message.body + '\n' + umessage
                message.body = message.body +'\n' + adminemail
                #print message.body
                dnd = ReviewTracking(parent=database_key(DEFAULT_DATABASE_NAME),
                                useremail = uemail,jobid=jobid,message=umessage,adminid=adminemail)
                dnd.state = 1
                try:
                        message.send()
                except apiproxy_errors.OverQuotaError, message:
                    #                        logging.error(message)
                        dnd.state=0
                        return 'Sorry! Daily Email Quota Exceeded.Process is moving forward - dont worry'
                        return 'Email has been rejected: '+ uemail + "@stevens.edu"
                dnd.put()
            if(actionid == 'close') :
        # Update the job id's state to scheduled
        # update machine
                adminuser = users.get_current_user()
                adminemail = adminuser.email()
                jobid=self.request.get('jobid')
                umessage =self.request.get('umessage')
                print umessage
                thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
                uemail = thisjob.useremail
                aemail = thisjob.advisoremail
                thisjob.state  = 6
                thisjob.reviewed = datetime.now()
                thisjob.put()
                subjectstr = 'Job closed and removed from queue by: Admin = '+ adminemail
                message = mail.EmailMessage(sender='proof-lab-jobrequests@appspot.gserviceaccount.com', subject = subjectstr)
                message.to = uemail + '@stevens.edu'
                #                message.cc = aemail + '@stevens.edu'
                message.body = 'Dear Student,\n  \n'
                message.body = message.body + '\n ** The job you submitted has been closed and deleted ** '
                message.body = message.body + '\n Reason: '
                message.body = message.body + '\n' + umessage
                message.body = message.body +'\n\n ** PLEASE DO NOT REPLY TO THIS EMAIL ** \n RESPOND DIRECTLY TO: ' + adminemail
                #print message.body
                dnd = ReviewTracking(parent=database_key(DEFAULT_DATABASE_NAME),
                                useremail = uemail,jobid=jobid,message=umessage,adminid=adminemail)
                dnd.state = 1
                try:
                        message.send()
                except apiproxy_errors.OverQuotaError, message:
                    #                        logging.error(message)
                        dnd.state=0
                        return 'Sorry! Daily Email Quota Exceeded. Please retry tomorrow. '
                dnd.put()
            if(actionid == 'deliver') :
        # Update the job id's state to scheduled
        # update machine
                adminuser = users.get_current_user()
                adminemail = adminuser.email()
                jobid=self.request.get('jobid')
                machineid =self.request.get('umachine')
                materialid =self.request.get('umaterial')
                upartvolume =self.request.get('upartvolume')
                usupportvolume =self.request.get('usupportvolume')
                ucosttolab =self.request.get('ulabcost')
                thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
                uemail = thisjob.useremail
                thisjob.state  = 5
                thisjob.delivered = datetime.now()
                thisjob.partvolume = upartvolume
                thisjob.machineassigned = machineid
                thisjob.partmaterial = materialid
                thisjob.engineer = adminemail
                thisjob.supportvolume = usupportvolume
                thisjob.costtolab = ucosttolab
                thisjob.delivered  = datetime.now()
                thisjob.put()
                subjectstr = 'Proof Lab Job Completed by:'+ adminemail
                message = mail.EmailMessage(sender='Proof Lab Job Requests <proof-lab-jobrequests@appspot.gserviceaccount.com>', subject = subjectstr)
                message.to = uemail + '@stevens.edu'
                message.body = 'Dear Student,\n ** PLEASE DO NOT REPLY TO THIS EMAIL ** \n'
                message.body = message.body + 'RESPOND DIRECTLY TO: '+ adminemail
                message.body = message.body + '\n' + '3D print job has been completed. \n Please pick it up from the lab '
                message.body = message.body + '\n' + 'Lab is located in Carnegie 1st Floor - Ring the bell. '
                message.body = '\n' + adminemail
                try:
                        message.send()
                except apiproxy_errors.OverQuotaError, message:
                    #                        logging.error(message)
                        return 'Sorry! Daily Email Quota Exceeded. The job has been accepted. '
        self.redirect("/admin")


class JobEditHandler(webapp2.RequestHandler):
    def get(self,resource1,resource2):
        #print resource1, resource2, resource3
        if IsUserAdmin() :
            jobid = str(urllib2.unquote(resource2))
            thisjob = LabJobsDB.get_by_id(int(jobid),parent=database_key(DEFAULT_DATABASE_NAME))
             # set up a form and load up the current values
            self.response.out.write(HEADER_STRING)
            if (resource1 == "schedule"):
                self.response.out.write("""
                    <form id="form2" class="form" name="form2" method="post" action="/jobupdate" >
                    <input type="hidden" class="text" id="actionid" name="actionid" value="schedule" />
                    <input type="hidden" class="text" id="jobid" name="jobid" value="%s" />
                    """ % str(resource2))
                self.response.out.write("""
                <h2 class="section">Scheduling Job from %s@stevens.edu </h2>
                <div id="section1" >
                <div class="field">
                <label for="Name">Machine Assigned:</label>
                <input type="text" id="umachine" name="umachine" value=%s />
                </div>
                <div class="field">
                <label for="Name">Material Assigned:</label>
                <input type="text" id="umaterial" name="umaterial" value=%s />
                </div>
                    <input type="submit" class="button" value="Update" />
                    </form> """ % (thisjob.useremail,thisjob.machineassigned, thisjob.partmaterial))
            if (resource1 == "review"):
                self.response.out.write("""
                    <form id="form2" class="form" name="form2" method="post" action="/jobupdate" >
                    <input type="hidden" class="text" id="actionid" name="actionid" value="review" />
                    <input type="hidden" class="text" id="jobid" name="jobid" value="%s" />
                    """ % ( str(resource2)))
                self.response.out.write("""
                    <h2 class="section">Reviewing Job from %s@stevens.edu </h2>
                    <div id="section1" >
                    <div class="field">
                    <label for="Name">Message to the user</label>
                    <textarea type="textarea" class="textarea" id="umessage" name="umessage" value="Message here."></textarea>
                    </div>
                    <input type="submit" class="button" value="Update" />
                    </form> """ % thisjob.useremail )
            if (resource1 == "close"):
                self.response.out.write("""
                    <form id="form2" class="form" name="form2" method="post" action="/jobupdate" >
                    <input type="hidden" class="text" id="actionid" name="actionid" value="close" />
                    <input type="hidden" class="text" id="jobid" name="jobid" value="%s" />
                    """ % ( str(resource2)))
                self.response.out.write("""
                    <h2 class="section">Closing Job from %s@stevens.edu </h2>
                    <div id="section1" >
                    <div class="field">
                    <label for="Name">Message the user and his advisor that this job has been closed/deleted and the reason
                    for doing so. </label>
                    <textarea type="textarea" class="textarea" id="umessage" name="umessage" value="Message here."></textarea>
                    </div>
                    <input type="submit" class="button" value="Update" />
                    </form> """ % thisjob.useremail )
            if (resource1 == "deliver"):
                self.response.out.write("""
                    <form id="form2" class="form" name="form2" method="post" action="/jobupdate" >
                    <input type="hidden" class="text" id="actionid" name="actionid" value="deliver" />
                    <input type="hidden" class="text" id="jobid" name="jobid" value="%s" />
                    """ % ( str(resource2)))
                self.response.out.write("""
                            <h2 class="section">Delivering Job from %s@stevens.edu </h2>
                            <div id="section1" >
                            <div class="field">
                            <label for="Name">Machine Assigned:</label>
                            <input type="text" id="umachine" name="umachine" value=%s />
                            </div>
                            <div class="field">
                            <label for="Name">Material Used:</label>
                            <input type="text" id="umaterial" name="umaterial" value=%s />
                            </div>
                            <div class="field">
                            <label for="Name">Part Volume/Weight:</label>
                            <input type="text" id="upartvolume" name="upartvolume" value=%s />
                            </div>
                            <div class="field">
                            <label for="Name">Support Volume/Weight:</label>
                            <input type="text" id="usupportvolume" name="usupportvolume" value=%s />
                            </div>
                            <div class="field">
                            <label for="Name">Cost to Lab:</label>
                            <input type="text" id="ulabcost" name="ulabcost" value=%s />
                            </div>
                            <input type="submit" class="button" value="Update" />
                            </form> """ % (thisjob.useremail,thisjob.machineassigned,
                                           thisjob.partmaterial, thisjob.partvolume,
                                           thisjob.supportvolume, thisjob.costtolab))
            self.response.out.write(FOOTER_STRING)
        else :
            self.response.out.write(HEADER_STRING)
            greeting = ("""<a href="%s" style="color:#ffffff"> 
                Admin login with an Authorized Google Account </a> """
                        % users.create_login_url('/'))
            self.response.out.write(" %s <p> <p> " % greeting)
            self.response.out.write(FOOTER_STRING)

class Filedump(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, resource):
        resource = str(urllib2.unquote(resource))
        blob_info = blobstore.BlobInfo.get(resource)
        self.send_blob(blob_info.key(),save_as=blob_info.filename)

class Fileserve(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, resource):
        resource = str(urllib2.unquote(resource))
        blob_info = blobstore.BlobInfo.get(resource)
        self.send_blob(blob_info.key())

def IsUserAdmin():
    user = users.get_current_user()
    if user:
        user = users.get_current_user()
        useremail  =  user.email()
        if (useremail in adminslist ):
            return True
    return False

class AdminHandler(webapp2.RequestHandler):
    def get(self):
        if IsUserAdmin():
            user = users.get_current_user()
            self.response.out.write(HEADER_STRING)
            self.response.write('<H2> Welcome, %s! (<a href="%s" style="color:blue">sign out</a>) </H2> ' %
                                (user.nickname(), users.create_logout_url('/')))
            qry = LabJobsDB.query().order(-LabJobsDB.created)
            slots= qry.fetch()
            self.response.write("""
                <h2> Create Reports: <A HREF="/reports/monthly"> Monthly Jobs </A> | <A HREF="/reports/costs"> Total Costs </A>  <p> Job Status List </h2> <p> <table id="table-3"> <thead> <th> Job No. </th> <th> User Name </th> <th> File </th> <th> Volume (cm^3) </th> <th> Bounding Box (cm) </th> <th> Status </th> <th> Action </th> </thead> <thead bgcolor="#D3D3D3"> <th> Advisor </th> <th> Section </th> <th> Material </th> <th colspan=6> Description
                </th> </thead> <tbody> """)
            jobcount = 0
            for slot in slots:
                jobcount = jobcount+1
                self.response.write(""" <tr> <td> %s <br> %s </td> <td> %s </td> <td> %s <BR> <A href=/dumper/%s> Download </A> |
                    <A href=/viewer/%s>   View  </A> </td> <td> %s </td> <td> %s </td>
                    <td> %s </td> """
                        % (str(jobcount),slot.created.strftime("%m-%d-%Y %H:%M"),slot.useremail, slot.filename, slot.stlblobkey, slot.stlblobkey,
                           slot.partvolume, slot.boundingbox,
                           statelist[slot.state]))
                if slot.state ==1 :
                    self.response.write(""" <td> <A HREF="/remindadvisor/%s/%s"> Email Advisor Again.  </A> <P> """
                                        % (str(slot.key.id()), slot.advisoremail))
                if(slot.state < 5 ):
                    self.response.write("""
                     <td> <A HREF="/jobedit/review/%s"> Review  </A> <P>
                     <A HREF="/jobedit/close/%s"> Close/Delete </A> </td>
                    <td> <A HREF="/jobedit/schedule/%s"> Schedule  </A>  </td>
                    <td> <A HREF="/jobedit/deliver/%s"> Deliver </A>  </td> """ %
                                (str(slot.key.id()), str(slot.key.id()), str(slot.key.id()), str(slot.key.id())))
                else:
                    self.response.write(""" <td colspan = 3>   """)
                self.response.write("""
                    </td> </tr>  """)
                self.response.write("""<tr bgcolor="#D3D3D3"> <td> %s </td> <td> %s </td> <td> %s </td><td colspan=6 > %s </td>
                             </tr>  """ % (slot.advisorname, slot.sdsection,slot.partmaterial,slot.description))
                self.response.write(""" <tr bgcolor="#000000"> <td colspan=9>  </td> </tr>  """)
            self.response.write("""  </tbody> </table> """)
            self.response.out.write(FOOTER_STRING)
        else:
            self.response.out.write(HEADER_STRING)
            greeting = ("""<h2> <a href="%s" style="color:blue">
                    Admin login with an Authorized Google Account </a> </h2>"""
                            % users.create_login_url('/admin'))
            self.response.out.write(" %s <p> <p> " % greeting)
            self.response.out.write(FOOTER_STRING)

# Render the left and right pages

class MainHandler(webapp2.RequestHandler):
    def get(self):
 #End of MainHandler Class
        self.response.out.write(HEADER_STRING)
        self.response.out.write(mainformheadhtml)
        self.response.write(identifyformfields)
#        self.response.out.write (""" <H2> Down for Maintenance ....   <BR>
#            <P> Please contact Mr. Biruk Gebre for information on your parts 
#            until Wednesday April 20th, 2016 <P> </H2> """)
        self.response.write(formtail)
        self.response.out.write(FOOTER_STRING)

class ViewHandler(webapp2.RequestHandler):
    def get(self,resource1):
         bloburl = "/blobserve/" +str(urllib2.unquote(resource1))
         htmlstring = file('view.html', 'rb').read()
         self.response.out.write( htmlstring.replace("$KISHORE$",bloburl))

class testSTL(webapp2.RequestHandler):
    def get(self,resource1):
        mySTLUtils = STLUtils()
        resource = str(urllib2.unquote(resource1))
        blob_info = blobstore.BlobInfo.get(resource)
        upartvolume = str(int(mySTLUtils.calculateVolume(str(blob_info.key()),"cm")))
        uboundingbox1 = mySTLUtils.boundingbox
        uboundingbox2 = [int(x / 10) for x in uboundingbox1]
        uboundingbox = str(uboundingbox2)
        print upartvolume
        print uboundingbox

class ReportsHandler(webapp2.RequestHandler):
    def get(self,resource1):
        self.response.out.write(HEADER_STRING)
        if IsUserAdmin():
            reportneeded = str(urllib2.unquote(resource1))
            if reportneeded == "monthly":
                self.response.out.write("""<center> <H2> MONTHLY JOBS REPORT  <BR>
                    <A HREF='/'> Back to login page </A> </H2></CENTER>""" )
            if reportneeded == "costs":
                self.response.out.write("""<center> <H2> COST REPORT  <BR>
                    <A HREF='/'> Back to login page </A> </H2></CENTER>
                    <table> <tr> <td> User Job # </td> <td> User Email </td> <td> Advisor Email </td> <td> File Name </td> <td> Cost to Lab </td> </tr>""")
                qry = LabJobsDB.query().order(-LabJobsDB.created)
                slots= qry.fetch()
                slotnum = 0
                for slot in slots:
                    if slot.state == 5:
                        slotnum = slotnum+1
                        self.response.out.write("""<tr> <td> %s </td><td> %s </td> <td>  %s </td> <td>  %s </td> <td>  %s </td> </tr> """ %
                                        (slotnum,slot.useremail,slot.advisoremail,slot.filename,slot.costtolab))
                self.response.out.write(""" </table>""")
        self.response.out.write(FOOTER_STRING)
# main application handler
class mailmeHandler(webapp2.RequestHandler):
    def get(self):
        message = mail.EmailMessage(sender='Proof Lab Job Requests <proof-lab-jobrequests@appspot.gserviceaccount.com>', subject = 'testing')
        message.to = 'Kpochira@stevens.edu'
        message.body = 'Dear Student, sending a link http://proof-lab-jobrequests/viewer/sdf9234sdfsadfa4y \n'
        message.body = message.body + 'RESPOND DIRECTLY TO: '
        try:
            message.send()
        except apiproxy_errors.OverQuotaError, message:
            #            logging.error(message)
            return 'Sorry! Daily Email Quota Exceeded. Please retry tomorrow. '

app = webapp2.WSGIApplication([
                               ('/', MainHandler),
                               ('/login', SignupHandler),
                               ('/dumper/([^/]+)?', Filedump),
                               ('/blobserve/([^/]+)?', Fileserve),
                               ('/computevolume', ComputeVolume),
                               ('/teststl/([^/]+)?', testSTL),
                               ('/withdraw/([^/]+)?', WidthdrawHandler),
                               ('/mailme', mailmeHandler),
                               ('/reports/([^/]+)?', ReportsHandler),
                               ('/remindadvisor/([^/]+)?/([^/]+)?', RemindAdvisor),
                               ('/advisorok([^/]+)?', AdvisorHandler),
                               ('/admin', AdminHandler),
                               ('/jobedit/([^/]+)?/([^/]+)?', JobEditHandler),
                               ('/jobupdate', JobUpdateHandler),
                               ('/viewer/([^/]+)?', ViewHandler),
                               ('/resend/([^/]+)?', ResendHandler),
                               ('/upload', UploadHandler)
                               ],  debug=True)
