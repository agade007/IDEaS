#!/usr/bin/env python
#
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

# Set up the session
#This is needed to configure the session secret key
#Runs first in the whole application
myconfig_dict = {}
myconfig_dict['webapp2_extras.sessions'] = {
    'secret_key': 'my-super-secret-key-121514141414',
    'session_max_age':300
}

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

# Databases and keys
DEFAULT_DATABASE_NAME = "PROOF_LAB_DATA"

class UserDB(ndb.Model):
    email = ndb.StringProperty(required=True )  #uemail
    name = ndb.StringProperty(required=True)    #uname
    created = ndb.DateTimeProperty(auto_now_add=True)
    accesscode = ndb.StringProperty(required=True) #ucode
    sdsection = ndb.StringProperty(required=True)  #usection
    projectname = ndb.StringProperty(required=True) #uproject
    sessionid = ndb.StringProperty(required=True)   #usession
    
class ProjectsDB(ndb.Model):
    advisoremail = ndb.StringProperty(required=True)
    projectname = ndb.StringProperty(required=True)

class UserJobs (ndb.Model):
    useremail = ndb.StringProperty(required=True)
    jobid  = ndb.StringProperty(required=True)
    lastmodified = ndb.DateTimeProperty(required=False)

class JobsDB(ndb.Model):
     state=ndb.IntegerProperty(required=True)
     # 1. created; 2. authorized; 3. Revisions 4. Scheduled 5. Delivered.
     engineer = ndb.StringProperty(required=True )
     stlfilekey = ndb.StringProperty(required=True )
     #time stamps
     created = ndb.DateTimeProperty(auto_now_add=True)
     authorized = ndb.DateTimeProperty(required=False)
     scheduled = ndb.DateTimeProperty(required=False)
     delivered = ndb.DateTimeProperty(required=False)

def database_key(database_name=DEFAULT_DATABASE_NAME):
    """Constructs a Datastore key ."""
    return ndb.Key('ProofLabJobs', database_name)

#login and user access code management

def KeyGenerator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

def SessionKeyGen(size=9, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

def EmailCodes(uemail,accesscode):
    subjectstr = "PROOF LAB Job Submission Access"
    message = mail.EmailMessage(sender='Proof Lab Job Requests <kishore.stevens@gmail.com>', subject = subjectstr)
    message.to = uemail + '@stevens.edu'
    message.body = 'Dear ' + uemail +', \n Your access Code is:  ' +accesscode
    message.body = message.body+ '\n Please return to the app to sign in. \n This is an auto-generated message. Do not reply to this address.'
    print message.body
    print message.to
    try:
        message.send()
    except apiproxy_errors.OverQuotaError, message:
        logging.error(message)
        return 'Sorry! Daily Email Quota Exceeded. Please retry tomorrow '
    return 'Access Code E-Mail has been Queued to: '+ uemail + "@stevens.edu"

###

HEADER_STRING = """<!DOCTYPE HTML>
    <html>
    <head>
    <title>Proof Lab Job Requests </title>
    <meta charset="UTF-8" />
    <script src="js/modernizr.js" type="text/javascript"></script>
    <link rel="stylesheet" href="css/reset.css">
    <link rel="stylesheet" href="css/style.css">
    </head>
    <body>
    """
FOOTER_STRING = """
    <script src='js/jquery.min.js'></script>
    <script src='js/rmr1zue.js'></script>
    <script src="js/index.js"></script>
    </body>
    </html>"""

def loginhtml(sessionid):
    print "sessionid = " + sessionid + ":"
    if not sessionid:
        html2 = """
        <form action="ProcessLogin" method="post">
        <label>
        <span>Your Name :</span>
        <input id="uname" type="text" name="uname" size=25 placeholder="Your Full Name"  required= "required"  />
        </label>
        <label><P>
        <span> Email:</span> <BR>
        <input id="uemail" type="txt" size=10 name="uemail" placeholder="astudent" required="required" /> <b>@stevens.edu </b>
        </label> <P>
        <label>
        <span>Access code:</span><BR>
        <input id="ucode" type="password"  name="ucode" placeholder="ABCDEF" />
        </label><BR>
        No Code? Leave code box blank. <P>
        <span> Senior Project (2015-2016) </span> <BR>
        <select name="uproject" style="width: 150px"  required= "required"  >
        <option value="" disabled selected>Select Project (Advisor) </option>
        <option value="projid">Project-A (Prof-A)</option>
        <option value="projid">Project-A (Prof-B)</option>
        </select>
        </label> <P>
        <label>
        <span>Senior Design Section  :</span>
        <select name="usection" style="width: 150px"  required= "required"  >
        <option value="" disabled selected>Select Section</option>
        <option value="BME423-A">BME423-A</option>
        <option value="CPE423-B">CPE423-B</option>
        <option value="E423-X">E423-X</option>
        <option value="E423-X1">E423-X1</option>
        <option value="E423-X2">E423-X2</option>
        <option value="EE423-A">EE423-A</option>
        <option value="EE423-B">EE423-B</option>
        <option value="EM423-A">EM423-A</option>
        <option value="EN423-A">EN423-A</option>
        <option value="CE423-A">CE423-A</option>
        <option value="CHE423-A">CHE423-A</option>
        <option value="ME423-A">ME423-A</option>
        <option value="ME423-B">ME423-B</option>
        <option value="NE423-A">NE423-A</option>
        <option value="Other">Not Listed</option>
        </select>
        </label> <P>
        <label>
        <span>&nbsp;</span>
        <input type="submit" class="button" value="Login" />
        </label>
        </form>
        """
    else:
        html2 = "Logged in as: "
    return html2


class ProcessLogin(BaseSessionHandler):
    def post(self):
        uname=self.request.get('uname')
        uemail=self.request.get('uemail')
        ucode=self.request.get('ucode')
        usection=self.request.get('usection')
        uproject = self.request.get('uproject')
        qry = UserDB.query(UserDB.email == uemail)
        if qry.iter(keys_only=True).has_next():
            userrecord = qry.fetch(1)
            # If email exists and code does not match, email code again
            accesscode = userrecord[0].accesscode
            if(accesscode == ucode):
                # Check if reservation exists
                self.session['session-key']=SessionKeyGen()
                self.session['session-user']=uemail
            else:
                self.session['session-error']='Incorrect Access Code'
                self.redirect('/')
                return
        else:
            # Create the user and email
            newkey = KeyGenerator()
            dnd = UserDB(parent=database_key(DEFAULT_DATABASE_NAME),sdsection=usection,
                         email=uemail, name=uname,accesscode=newkey,sessionid='None', projectname=uproject)
            dnd.put()
            self.response.out.write("""<center> <H3> A new access key has been created. Please check  %s@stevens.edu
                             to get the code.    """ % uemail)
            eresponse=EmailCodes(uemail,newkey)
            self.response.out.write("""</H3>  </center>""")
            # New code created or code did not match. Code was sent to your addresss.
            self.response.out.write(FOOTER_STRING)
        self.redirect('/')

def logouthtml(sessionid):
    html2 = """
        <form action="ProcessLogin" method="post">
        <label>
        <span>&nbsp;</span>
        <input type="submit" class="button" value="Logout" />
        </label>
        </form>
        """
    return html2

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

def jobsubmitform(sessionid):
    upload_url = blobstore.create_upload_url('/upload')
    print upload_url
    html2 = """
        <form action="%s" method="post" enctype="multipart/form-data">
        <label>
        <span>Part Name/Identifier:</span>
        <input id="pname" type="text" name="pname" size=30 placeholder="Part Number"  required= "required"  />
        </label> <p>
        <label>
        <span>Upload Stl part file:</span>
        <input type="file" name="file" required/>
        </label> <p>
        <label>
        <span>&nbsp;</span>
        <input type="submit" class="button" value="Submit Job" />
        </label>
        </form>
        """ % upload_url
    return html2

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler,webapp2.RequestHandler):
    def post(self):
        auname=self.request.get('pname')
        print auname
        if(len(auname) == 0 ):
            self.redirect('/')
            return
        aufile=self.request.get('file')
        print auname
        if(len(aufile) == 0 ):
            self.redirect('/')
            return
        timestampnow = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp2 =datetime.now().strftime("%Y-%m-%d-%H_%M_%S")
    # Upload the file into a blob
        upload_files = self.get_uploads('file')  # 'file' is file upload field in the form
        if(len(upload_files) == 0 ):
             print "Upload file had no data "
             return
        blob_info = upload_files[0]
        blob_reader = blobstore.BlobReader(blob_info)
        attfile  =  auname +"_"+timestamp2+ "_"+ blob_info.filename
        if(blob_info.size > 20971520*4):
            self.response.out.write('<br> File Rejected. ERROR: FILE SIZE IS ABOVE LIMIT (80 MB). Please Resubmit <BR>')
            return
        self.response.out.write(' <br> File Received </h1> Received from: %s  at UTC %s  <br>' % (auname, timestampnow))
        self.response.out.write(' File received was: %s type: %s <br>' % (blob_info.filename,blob_info.content_type))
#        self.response.out.write(' File has been written to Google Drive %s <br>' % attfile)


# Render the left and right pages

def leftmenurender(sessionid):
    htmlstring = """
        <div class="accordion">
        <dl>
        <dt class="active"><a href="#"><span class="arrow"></span>Login/Register  </a></dt>
            <dd class="active"> """ + loginhtml(sessionid) + """
            </dd>
            <dt><a href="#"><span class="arrow"></span> Consult Request </a></dt>
            <dd> """ + consultform(sessionid) + """
            </dd>
            <dt><a href="#"><span class="arrow"></span>Submit a Job </a></dt>
            <dd> """ + jobsubmitform(sessionid) + """
            </dd>
            <dt><a href="#"><span class="arrow"></span> Logout </a></dt>
            <dd> """ + logouthtml(sessionid) + """
            </dd>
        </dl>
        </div>
        """
    return htmlstring

def tabpagerender(sessionid):
    htmlstring ="""
        <section class="wrapper">
        <ul class="tabs">
        <li><a href="#tab1">Instructions & Help  </a></li>
        <li><a href="#tab3">Machine Status </a></li> """
    if sessionid != 'None':
        htmlstring= htmlstring + """ 
        <li><a href="#tab2">Job Status  </a></li>
        <li><a href="#tab4">Stl Viewer </a></li>"""
    htmlstring = htmlstring +"""
        </ul>
        <div class="clr"></div>
        <section class="block">
        <article id="tab1">
        <H1> Instructions and Tutorials </H1>
        <b> Job Submission Procedures </b>
        <ul> <li> -2. Design the part in 3D CAD and Generate an STL File. </li>
        <li> -1.Create an account here with your email and identify your project. </li>
        <li>  0.  Login into this system  </li>
        <li> 1. If you need, submit the stl file and get a design consult.  </li>
        <li> 2. Submit a job using the Submit Job form </li>
        <li> 3. Your advsior will get an email asking for authorization. Email will contain your name, project name, your email address, and a link to authorize only. Parts not authorized for print within 72 hours will be automatically deleted from the system. Contact your advisor to expedite the process.
        <li> 4. You may get an email from one of the lab's engineers if there are issues with the part. If there are no issues, the parts will be printed and you will receive an email with pick up date/time.
        </ul>        </article>
        <article id="tab2">
        <p>Sed egestas, ante et vulputate volutpat, eros pede semper est, vitae luctus metus libero eu augue. Morbi purus libero, faucibus adipiscing, commodo quis, gravida id, est. Sed lectus. Praesent elementum hendrerit tortor. Sed semper lorem at felis. Vestibulum volutpat, lacus a ultrices sagittis, mi neque euismod dui, eu pulvinar nunc sapien ornare nisl. Phasellus pede arcu, dapibus eu, fermentum et, dapibus sed, urna.</p>
        </article>    """
    if sessionid != 'None':
        htmlstring = htmlstring+"""
        <article id="tab3">
        <p>Morbi interdum mollis sapien. Sed ac risus. Phasellus lacinia, magna a ullamcorper laoreet, lectus arcu pulvinar risus, vitae facilisis libero dolor a purus. Sed vel lacus. Mauris nibh felis, adipiscing varius, adipiscing in, lacinia vel, tellus. Suspendisse ac urna. Etiam pellentesque mauris ut lectus. Nunc tellus ante, mattis eget, gravida vitae, ultricies ac, leo. Integer leo pede, ornare a, lacinia eu, vulputate vel, nisl.</p>
        </article>
        <article id="tab4">
        <p>Morbi interdum mollis sapien. Sed ac risus. Phasellus lacinia, magna a ullamcorper laoreet, lectus arcu pulvinar risus, vitae facilisis libero dolor a purus. Sed vel lacus. Mauris nibh felis, adipiscing varius, adipiscing in, lacinia vel, tellus. Suspendisse ac urna. Etiam pellentesque mauris ut lectus. Nunc tellus ante, mattis eget, gravida vitae, ultricies ac, leo. Integer leo pede, ornare a, lacinia eu, vulputate vel, nisl.</p>
        </article>
        </section>
        </section> """
    return htmlstring

class MainHandler(BaseSessionHandler):
    def get(self):
        sessionid = self.session.get('session-id')
        print sessionid
        if not sessionid:
            sessionid = 'None'
 #End of MainHandler Class
        self.response.out.write(HEADER_STRING)
        html_string = """
            <div id="header">
            <h1> PROtotype Object Fabrication (PROOF) Laboratory <P> <P>  Job Requests </h1> <P>
            </div>
                <div class="colmask leftmenu">
                    <div class="colleft">
                        <div class="col1"> """ + tabpagerender(sessionid) + """
                        </div>
                        <div class="col2"> """ + leftmenurender(sessionid) + """
                        </div>
                    </div>
                </div>
        """
        self.response.write(html_string)
        self.response.out.write(FOOTER_STRING)

# main application handler

app = webapp2.WSGIApplication([
                               ('/', MainHandler),
                               ('/upload', UploadHandler),
                               ('/ProcessLogin', ProcessLogin)
                               #    ('/Admin', AdminMain),
                               #('/ProcessRequest', RequestHandler)
                               ], config = myconfig_dict, debug=True)