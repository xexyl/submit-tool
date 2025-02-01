#!/usr/bin/env python3
#
# ioccc.py - Core functions that of the IOCCC submit tool web application
#
# pylint: disable=invalid-overridden-method
# pylint: disable=too-many-statements
# pylint: disable=too-many-lines

"""
ioccc.py - Core functions that of the IOCCC submit tool web application

This code is based on code originally written by Eliot Lear (@elear) in late 2021.
The [IOCCC judges](https://www.ioccc.org/judges.html) heavily modified
Eliot's code, so any fault you find should be blamed on them 😉 (that is, the
IOCCC Judges :-) ).

NOTE: This flask-login was inspired by the following:

    https://github.com/costa-rica/webApp01-Flask-Login/tree/github-main
    https://nrodrig1.medium.com/flask-login-no-flask-sqlalchemy-d62310bb43e3
"""


# system imports
#
import inspect
import re
import subprocess

# import from modules
#
from pathlib import Path


# 3rd party imports
#
from flask import Flask, render_template, request, redirect, url_for, flash, render_template_string
import flask_login
from flask_login import current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# import the ioccc common utility code
#
# Sort the import list with: sort -d -u
#
# pylint: disable-next=unused-import
from iocccsubmit.ioccc_common import \
    APPDIR, \
    MAX_PASSWORD_LENGTH, \
    MAX_TARBALL_LEN, \
    MIN_PASSWORD_LENGTH, \
    contest_is_open, \
    debug, \
    error, \
    get_all_json_slots, \
    info, \
    initialize_user_tree, \
    is_proper_password, \
    lookup_username, \
    must_change_password, \
    return_client_ip, \
    return_last_errmsg, \
    return_secret, \
    return_slot_dir_path, \
    return_user_dir_path, \
    update_password, \
    update_slot, \
    user_allowed_to_login, \
    verify_hashed_password, \
    warning


# ioccc.py version
#
# NOTE: Use string of the form: "x.y[.z] YYYY-MM-DD"
#
VERSION_IOCCC = "2.5.2 2025-01-31"


# Configure the application
#
application = Flask(__name__,
            template_folder=f'{APPDIR}/templates',
            root_path=APPDIR)
application.config['MAX_CONTENT_LENGTH'] = MAX_TARBALL_LEN
application.config['FLASH_APP'] = "iocccsubmit"
application.debug = False
application.config['FLASK_ENV'] = "production"
application.config['TEMPLATES_AUTO_RELOAD'] = False
application.secret_key = return_secret()


# Set application file paths
#
with application.test_request_context('/'):
    url_for('static', filename='style.css')
    url_for('static', filename='script.js')
    url_for('static', filename='ioccc.png')


# Setup the login manager
#
login_manager = flask_login.LoginManager()
login_manager.init_app(application)

# determine our storage URI for the Flask limiter
#
# case: We have memcached installed - use memcached port
#
if Path("/etc/sysconfig/memcached").is_file():

    # Check if memcached is running properly
    #
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', '--quiet', 'memcached'],
            check=True
        )
        STORAGE_URI = "memcached://127.0.0.1:11211"
    except subprocess.CalledProcessError:
        warning("Memcached configuration file exists, but memcached is not running. Falling back to memory storage.")
        STORAGE_URI = "memory://"

# else: use just local memory
#
else:
    STORAGE_URI = "memory://"


# Setup for default the Flask limiter
#
limiter = Limiter(
    get_remote_address,
    default_limits = ["8 per minute"],
    app = application,
    storage_uri = STORAGE_URI,
)


# IP address based limits
#
ip_based_limit = limiter.limit(
    limit_value = "8 per minute",
    key_func = get_remote_address,
    per_method = True,
    error_message = (
        # pylint: disable-next=f-string-without-interpolation
        f'Too much too often!!  You have exceeded a reasonable rate limit.\n'
        f'\n'
        f'You have been put into the \"penalty box\" for a period of time until you slow down.'),
    override_defaults = True,
    scope = "IPv4",
)


# Username based limits
#
user_based_limit = limiter.shared_limit(
    limit_value = "8 per minute",
    key_func = lambda : current_user.id,
    per_method = True,
    error_message = (
        # pylint: disable-next=f-string-without-interpolation
        f'You\'re going too Fast!!  You have exceeded a reasonable rate limit.\n'
        f'\n'
        f'You have been put into the \"penalty box\" for a period of time until you slow down.'),
    override_defaults = True,
    scope = "user",
)


# Trivial user class
#
@limiter.exempt
class User(flask_login.UserMixin):
    """
    Trivial user class
    """
    user_dict = None
    id = None
    authenticated = False

    def __init__(self, username):
        self.user_dict = lookup_username(username)
        if self.user_dict:
            self.id = username

    def is_active(self):
        """True, as all users are active."""
        return True

    def get_id(self):
        """Return the username to satisfy Flask-Login's requirements."""
        return self.id

    def is_authenticated(self):
        """Return True if the user is authenticated."""
        return self.authenticated

    def is_anonymous(self):
        """False, as anonymous users aren't supported."""
        return False


@login_manager.user_loader
@limiter.exempt
def user_loader(user_id):
    """
    load the user
    """
    user =  User(user_id)
    if user.id:
        return user
    return None


# pylint: disable=too-many-return-statements
#
@application.route('/', methods = ['GET', 'POST'])
@ip_based_limit
def login():
    """
    Process login request
    """

    # setup
    #
    me = inspect.currentframe().f_code.co_name

    # case: process / POST
    #
    if request.method == 'POST':
        debug(f'{me}: {return_client_ip()}: '
              f'start POST')
        form_dict = request.form.to_dict()
        username = form_dict.get('username')

        # case: If the user is valid known user
        #
        user = User(username)
        if not user.id:
            info(f'{me}: {return_client_ip()}: '
                 f'invalid username')
            flash("ERROR: invalid username and/or password")
            return render_template('login.html')

        # validate password
        #
        if verify_hashed_password(form_dict.get('password'),
                                  user.user_dict['pwhash']):

            # case: If the user is not allowed to login
            #
            if not user_allowed_to_login(user.user_dict):
                info(f'{me}: {return_client_ip()}: '
                     f'disabled: username: {username}')
                flash("ERROR: Sorry (tm Canada 🇨🇦) you cannot login at this time")
                return render_template('login.html')

            # case: username and password are good, complete the login
            #
            user.authenticated = True
            flask_login.login_user(user)
            info(f'{me}: {return_client_ip()}: '
                 f'success: username: {username}')

        # case: invalid password
        #
        else:
            info(f'{me}: {return_client_ip()}: '
                 f'invalid password: username: {username}')
            flash("ERROR: invalid username and/or password")
            return render_template('login.html')

        # get the JSON slots for the user and verify we have slots
        #
        slots = initialize_user_tree(username)
        if not slots:
            error(f'{me}: {return_client_ip()}: '
                  f'username: {username} initialize_user_tree failed: {return_last_errmsg()}')
            flash(f'ERROR: in {me}: initialize_user_tree failed: {return_last_errmsg()}')
            flask_login.logout_user()
            info(f'{me}: {return_client_ip()}: '
                 f'forced logout for username: {username}')
            return render_template('login.html')

        # case: user is required to change password
        #
        if must_change_password(user.user_dict):
            info(f'{me}: {return_client_ip()}: '
                 f'required password change: username: {username}')
            flash("Notice: You are required to change your password")
            return redirect(url_for('passwd'))

        # render based on if the contest is open or not
        #
        close_datetime = contest_is_open(user.user_dict)
        if close_datetime:

            # case: contest open - both login and user setup are successful
            #
            return render_template('submit.html',
                                   flask_login = flask_login,
                                   username = username,
                                   etable = slots,
                                   date=str(close_datetime).replace('+00:00', ''))

        # case: contest is not open - both login and user setup are successful
        #
        info(f'{me}: {return_client_ip()}: '
             f'IOCCC is not open for username: {username}')
        flash("The IOCCC is not open")
        return render_template('not-open.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots)

    # case: process / GET
    #
    debug(f'{me}: {return_client_ip()}: '
          f'start GET')
    return render_template('login.html')
#
# pylint: enable=too-many-return-statements


# pylint: disable=too-many-branches
# pylint: disable=too-many-return-statements
#
@application.route('/submit', methods = ['GET', 'POST'])
@flask_login.login_required
@user_based_limit
def submit():
    """
    Access the IOCCC Submission Page - Upload a file to a user's slot
    """

    # setup
    #
    me = inspect.currentframe().f_code.co_name

    # get username
    #
    debug(f'{me}: {return_client_ip()}: '
          f'start')
    if not current_user.id:
        warning(f'{me}: {return_client_ip()}: '
                f'login required')
        flash("ERROR: Login required")
        flask_login.logout_user()
        info(f'{me}: {return_client_ip()}: '
             f'forced logout for current_user.id as None')
        return redirect(url_for('login'))

    # paranoia
    #
    username = current_user.id
    if not username:
        warning(f'{me}: {return_client_ip()}: '
                f'invalid username')
        flash("ERROR: Login required")
        flask_login.logout_user()
        info(f'{me}: {return_client_ip()}: '
             f'forced logout for username as None')
        return redirect(url_for('login'))

    # setup for user
    #
    user_dir = return_user_dir_path(username)
    if not user_dir:
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} return_user_dir_path failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: return_user_dir_path failed: {return_last_errmsg()}')
        flask_login.logout_user()
        info(f'{me}: {return_client_ip()}: '
             f'forced logout for username: {username}')
        return redirect(url_for('login'))

    # get the JSON for all slots for the user
    #
    slots = get_all_json_slots(username)
    if not slots:
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} get_all_json_slots failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: get_all_json_slots failed: {return_last_errmsg()}')
        flask_login.logout_user()
        info(f'{me}: {return_client_ip()}: '
             f'forced logout for username: {username}')
        return redirect(url_for('login'))

    # case: user is required to change password
    #
    if must_change_password(current_user.user_dict):
        info(f'{me}: {return_client_ip()}: '
             f'required password change: username: {username}')
        flash("User is required to change their password")
        return redirect(url_for('passwd'))

    # verify that the contest is still open
    #
    close_datetime = contest_is_open(current_user.user_dict)
    if not close_datetime:
        info(f'{me}: {return_client_ip()}: '
             f'IOCCC is not open for username: {username}')
        flash("The IOCCC is not open.")
        return render_template('not-open.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots)

    # verify they selected a slot number to upload
    #
    if not 'slot_num' in request.form:
        debug(f'{me}: {return_client_ip()}: '
              f'No slot selected')
        flash("No slot selected")
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))
    user_input = request.form['slot_num']
    try:
        slot_num = int(user_input)
    except ValueError:
        debug(f'{me}: {return_client_ip()}: '
              f'Slot number is not a number')
        flash("Slot number is not a number: " + user_input)
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # verify slot number
    #
    slot_dir = return_slot_dir_path(username, slot_num)
    if not slot_dir:
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} slot_num: {slot_num} '
              f'return_slot_dir_path failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: return_slot_dir_path failed: {return_last_errmsg()}')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # verify they selected a file to upload
    #
    if 'file' not in request.files:
        debug(f'{me}: {return_client_ip()}: '
              f'No file part')
        flash('No file part')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))
    file = request.files['file']
    if file.filename == '':
        debug(f'{me}: {return_client_ip()}: '
              f'No selected file')
        flash('No selected file')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # verify that the filename is in a submit file form
    #
    re_match_str = f'^submit\\.{username}-{slot_num}\\.[1-9][0-9]{{9,}}\\.txz$'
    if not re.match(re_match_str, file.filename):
        debug(f'{me}: {return_client_ip()}: '
              f'username: {username} slot_num: {slot_num} invalid form of a filename')
        flash(f'Filename for slot: {slot_num} must match this regular expression: {re_match_str}')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # save the file in the slot
    #
    upload_file = f'{user_dir}/{slot_num}/{file.filename}'
    file.save(upload_file)
    if not update_slot(username, slot_num, upload_file):
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} slot_num: {slot_num} update_slot failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: update_slot failed: {return_last_errmsg()}')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # report on the successful upload
    #
    info(f'{me}: {return_client_ip()}: '
         f'username: {username} slot_num: {slot_num} uploaded: {file.filename}')
    flash("Uploaded file: " + file.filename)
    return render_template('submit.html',
                           flask_login = flask_login,
                           username = username,
                           etable = slots,
                           date=str(close_datetime).replace('+00:00', ''))
#
# pylint: enable=too-many-branches
# pylint: enable=too-many-return-statements


# pylint: disable=too-many-branches
# pylint: disable=too-many-return-statements
#
@application.route('/update', methods=["POST"])
@flask_login.login_required
@user_based_limit
def upload():
    """
    Upload slot file
    """

    # setup
    #
    me = inspect.currentframe().f_code.co_name

    # get username
    #
    debug(f'{me}: {return_client_ip()}: '
          f'start')
    if not current_user.id:
        warning(f'{me}: {return_client_ip()}: '
                f'login required')
        flash("ERROR: Login required")
        return redirect(url_for('login'))
    username = current_user.id
    # paranoia
    if not username:
        warning(f'{me}: {return_client_ip()}: '
                f'invalid username')
        flash("ERROR: Login required")
        return redirect(url_for('login'))

    # get the JSON for all slots for the user
    #
    slots = get_all_json_slots(username)
    if not slots:
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} get_all_json_slots failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: get_all_json_slots failed: {return_last_errmsg()}')
        return redirect(url_for('login'))

    # setup for user
    #
    user_dir = return_user_dir_path(username)
    if not user_dir:
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} return_user_dir_path failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: return_user_dir_path failed: {return_last_errmsg()}')
        return redirect(url_for('login'))

    # case: user is required to change password
    #
    if must_change_password(current_user.user_dict):
        info(f'{me}: {return_client_ip()}: '
             f'username: {username} required password change')
        flash("User is required to change their password")
        return redirect(url_for('passwd'))

    # verify that the contest is still open
    #
    close_datetime = contest_is_open(current_user.user_dict)
    if not close_datetime:
        info(f'{me}: {return_client_ip()}: '
             f'IOCCC is not open for username: {username}')
        flash("The IOCCC is not open.")
        return render_template('not-open.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots)

    # verify they selected a slot number to upload
    #
    if not 'slot_num' in request.form:
        debug(f'{me}: {return_client_ip()}: '
              f'username: {username} No slot selected')
        flash("No slot selected")
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))
    user_input = request.form['slot_num']
    try:
        slot_num = int(user_input)
    except ValueError:
        debug(f'{me}: {return_client_ip()}: '
              f'username: {username} Slot number is not a number')
        flash("Slot number is not a number: " + user_input)
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # verify slot number
    #
    slot_dir = return_slot_dir_path(username, slot_num)
    if not slot_dir:
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} slot_num: {slot_num} '
              f'return_slot_dir_path failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: return_slot_dir_path failed: {return_last_errmsg()}')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # verify they selected a file to upload
    #
    if 'file' not in request.files:
        debug(f'{me}: {return_client_ip()}: '
              f'username: {username} No file part')
        flash('No file part')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))
    file = request.files['file']
    if file.filename == '':
        debug(f'{me}: {return_client_ip()}: '
              f'username: {username} No selected file')
        flash('No selected file')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # verify that the filename is in a submit file form
    #
    re_match_str = f'^submit\\.{username}-{slot_num}\\.[1-9][0-9]{{9,}}\\.txz$'
    if not re.match(re_match_str, file.filename):
        debug(f'{me}: {return_client_ip()}: '
              f'username: {username} slot_num: {slot_num} invalid form of a filename')
        flash(f'Filename for slot: {slot_num} must match this regular expression: {re_match_str}')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # save the file in the slot
    #
    upload_file = f'{user_dir}/{slot_num}/{file.filename}'
    file.save(upload_file)
    if not update_slot(username, slot_num, upload_file):
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} slot_num: {slot_num} update_slot failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: update_slot failed: {return_last_errmsg()}')
        return render_template('submit.html',
                               flask_login = flask_login,
                               username = username,
                               etable = slots,
                               date=str(close_datetime).replace('+00:00', ''))

    # report on the successful upload
    #
    info(f'{me}: {return_client_ip()}: '
         f'username: {username} slot_num: {slot_num} uploaded: {file.filename}')
    flash("Uploaded file: " + file.filename)

    # both login and user setup are successful
    #
    return render_template('submit.html',
                           flask_login = flask_login,
                           username = username,
                           etable = get_all_json_slots(username),
                           date=str(close_datetime).replace('+00:00', ''))
#
# pylint: enable=too-many-branches
# pylint: enable=too-many-return-statements


@application.route('/logout')
@ip_based_limit
def logout():
    """
    Logout.
    """

    # setup
    #
    me = inspect.currentframe().f_code.co_name

    # determine username if possible
    #
    debug(f'{me}: {return_client_ip()}: '
          f'start')
    username = "((unknown user))"
    if current_user and current_user.id:
        username = current_user.id

    # logout
    #
    flask_login.logout_user()
    info(f'{me}: {return_client_ip()}: '
         f'logout for username: {username}')
    return redirect(url_for('login'))


# pylint: disable=too-many-branches
# pylint: disable=too-many-return-statements
# pylint: disable=too-many-statements
#
@application.route('/passwd', methods = ['GET', 'POST'])
@user_based_limit
def passwd():
    """
    Change user password
    """

    # setup
    #
    me = inspect.currentframe().f_code.co_name

    # get username
    #
    debug(f'{me}: {return_client_ip()}: '
          f'start')
    if not current_user.id:
        warning(f'{me}: {return_client_ip()}: '
                f'login required #0')
        flash("ERROR: Login required")
        return redirect(url_for('login'))
    username = current_user.id
    # paranoia
    if not username:
        warning(f'{me}: {return_client_ip()}: '
                f'invalid username #0')
        flash("ERROR: Login required")
        return redirect(url_for('login'))

    # get the JSON for all slots for the user
    #
    slots = get_all_json_slots(username)
    if not slots:
        error(f'{me}: {return_client_ip()}: '
              f'username: {username} get_all_json_slots failed: {return_last_errmsg()}')
        flash(f'ERROR: in: {me}: get_all_json_slots failed: {return_last_errmsg()}')
        return redirect(url_for('login'))

    # case: process passwd POST
    #
    if request.method == 'POST':
        debug(f'{me}: {return_client_ip()}: '
              f'start POST')
        form_dict = request.form.to_dict()

        # If the user is allowed to login
        #
        user = User(username)
        if user.id:

            # get username
            #
            if not current_user.id:
                warning(f'{me}: {return_client_ip()}: '
                        f'login required #1')
                flash("ERROR: Login required")
                return redirect(url_for('login'))
            # paranoia
            if not username:
                warning(f'{me}: {return_client_ip()}: '
                        f'invalid username #1')
                flash("ERROR: Login required")
                return redirect(url_for('login'))

            # get form parameters
            #
            old_password = form_dict.get('old_password')
            if not old_password:
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} No current password')
                flash("ERROR: You must enter your current password")
                return redirect(url_for('login'))
            new_password = form_dict.get('new_password')
            if not new_password:
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} No new password')
                flash("ERROR: You must enter a new password")
                return redirect(url_for('login'))
            reenter_new_password = form_dict.get('reenter_new_password')
            if not reenter_new_password:
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} No reentered password')
                flash("ERROR: You must re-enter the new password")
                return redirect(url_for('login'))

            # verify new and reentered passwords match
            #
            if new_password != reenter_new_password:
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} new password not same as reentered password')
                flash("ERROR: New Password and Reentered Password are not the same")
                return redirect(url_for('passwd'))

            # disallow old and new passwords being substrings of each other
            #
            if new_password == old_password:
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} new password same as current password')
                flash("ERROR: New password cannot be the same as your current password")
                return redirect(url_for('passwd'))
            if new_password in old_password:
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} new password contains current password')
                flash("ERROR: New password must not contain your current password")
                return redirect(url_for('passwd'))
            if old_password in new_password:
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} current password contains new password')
                flash("ERROR: Your current password cannot contain your new password")
                return redirect(url_for('passwd'))

            # validate new password
            #
            if not is_proper_password(new_password):
                debug(f'{me}: {return_client_ip()}: '
                      f'username: {username} new password rejected')
                flash("ERROR: New Password is not a valid password")
                flash(return_last_errmsg())
                return redirect(url_for('passwd'))

            # change user password
            #
            # NOTE: This will also validate the old password
            #
            if not update_password(username, old_password, new_password):
                error(f'{me}: {return_client_ip()}: '
                      f'username: {username} failed to change password')
                flash("ERROR: Password not changed")
                flash(return_last_errmsg())
                return redirect(url_for('passwd'))

            # user password change successful
            #
            info(f'{me}: {return_client_ip()}: '
                 f'password changed for username: {username}')
            flash("Password successfully changed")
            return redirect(url_for('logout'))

    # case: process /passwd GET
    #
    debug(f'{me}: {return_client_ip()}: '
          f'start GET')
    pw_change_by = current_user.user_dict['pw_change_by']
    return render_template('passwd.html',
                           flask_login = flask_login,
                           username = username,
                           pw_change_by = pw_change_by,
                           min_length = str(MIN_PASSWORD_LENGTH),
                           max_length = str(MAX_PASSWORD_LENGTH))
#
# pylint: enable=too-many-branches
# pylint: enable=too-many-return-statements
# pylint: enable=too-many-statements


# pylint: disable=unused-argument
#
# Handle standard rate limit errors.
#
@application.errorhandler(429)
def ratelimit_error_handler(e):
    """
    Handle normal rate limit errors with a nice friendly error message.
    """
    return render_template_string(
        """
        <html>
            <head>
                <title>Slow Down, Friend!</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        text-align: center;
                        background-color: #f0f8ff;
                        color: #333;
                        margin-top: 50px;
                    }
                    .container {
                        margin: 0 auto;
                        padding: 20px;
                        max-width: 600px;
                        border: 2px solid #ddd;
                        border-radius: 10px;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    }
                    h1 {
                        color: #2a7ae2;
                    }
                    p {
                        font-size: 1.2rem;
                        margin-top: 10px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Wait a minute!</h1>
                    <h2>Take a Deep Breath!</h2>
                    <p>You've been making requests a bit too quickly.</p>
                    <p>Please slow down, relax, pet the cat, drink a calming cup of tea,<br>
                       and try again later.</p>
                </div>
            </body>
        </html>
        """
    ), 429
#
# pylint: enable=unused-argument


# catch all other URLs
#
# We reject with an HTTP error, the attempt as if they were a system cracker.
#
@application.route('/', defaults={'path': ''})
@application.route('/<path:_path>')
@limiter.exempt
def system_cracker(_path):
    """Block unauthorized access attempts."""
    return "Go away, system cracker!", 418
