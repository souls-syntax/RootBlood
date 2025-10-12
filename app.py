from flask import Flask, jsonify, request
import docker
import os
from flask_sqlalchemy import SQLAlchemy
import uuid
import subprocess
import time
from sqlalchemy.exc import IntegrityError
import pwd, grp
import shutil
from datetime import datetime, timezone, timedelta
import threading
import sys

# App Configs

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Docker config

docker_client = docker.from_env()
IMAGE_NAME = 'chaospine:1.0.0'
base_playground_path = os.path.join(basedir, 'global_playground')
SESSION_TTL_SECONDS = 5*60

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)

class Directory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(200), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner = db.relationship('User', backref=db.backref('directories', lazy=True))

class Contribution(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    owner_directory_path = db.Column(db.String(256), nullable=False)
    upperdir_path = db.Column(db.String(256), unique=True, nullable=False)
    directory_id = db.Column(db.Integer, db.ForeignKey('directory.id'), nullable=False)
    directory = db.relationship('Directory', backref=db.backref('contributions', lazy=True, cascade="all, delete-orphan"))


# Keeping it isolated as it only have one job
class ActiveSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.String(64), unique=True, nullable=False)
    container_name = db.Column(db.String(128), unique=True, nullable=False)
    last_active = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# Implementation

def track_session(container):
    with app.app_context():
        session = ActiveSession.query.filter_by(container_id=container.id).first()
        if not session:
            new_session = ActiveSession(container_id=container.id, container_name=container.name)
            db.session.add(new_session)
            db.session.commit()

def create_or_start_user_session(username):
    container_name = f"lpine_session_{username}"
    volume_name = f"{username}_home"

    try:
        container = docker_client.containers.get(container_name)

        if container.status !='running':
            print(f"Found stopped container for {username}. Starting it...")
            container.start()
        else:
            print(f"Container for {username} is already running.")
    except docker.errors.NotFound:
        print(f"No container found for {username}. Creating a new one...")
        docker_client.containers.run(
            IMAGE_NAME, 
            detach=True,
            name=container_name, 
            volumes={volume_name:{'bind':f'/home/{username}/', 'mode':'rw'},
                    base_playground_path:{'bind':'/global/','mode':'rw'}},
            ports={'7681/tcp': None}, 
            working_dir=f'/home/{username}',
            stdin_open=True, 
            tty=True
            )
        
        #s = client.attach_socket(container, {'stdin': 1, 'stdout': 1, 'stream':1})
        #s._sock.setblocking(False)
    
    container = docker_client.containers.get(container_name)
    container.reload()
    track_session(container)
    # container = docker_client.attach_socket(container, {'stdin': 1, 'stdout': 1, 'stream':1})
    # container._sock.setblocking(False)
    host_port = container.ports['7681/tcp'][0]['HostPort']
    return {"session_url":f"http://127.0.0.1:{host_port}","container_name":container_name}

def create_guest_session():
    container_name = f"chaotic_guest{uuid.uuid4().hex[:8]}"
    print(f"Creating new container {container_name}")

    container = docker_client.containers.run(
        IMAGE_NAME,
        detach=True,
        name=container_name,
        auto_remove=True,
        read_only=True,
        volumes={base_playground_path: {'bind': '/global', 'mode': 'ro'}},
        tmpfs={'/guest/' : ''},
        working_dir='/guest/',
        ports={'7681/tcp': None}, 
        stdin_open=True, 
        tty=True
    )
    container.reload()
    track_session(container)
    host_port = container.ports['7681/tcp'][0]['HostPort']
    return {"session_url":f"http://127.0.0.1:{host_port}","container_name":container_name}


# @Create a new function create_contributor_session(owner_username, contributor_username).

# @Inside it, define the paths for the lowerdir, upperdir, and workdir.

# @Construct the full docker run command string.

# @Use Python's subprocess.run(command, shell=True) to execute it.


def create_contributor_session(owner_username, contributor_username, project_name, directory):

    owner_project_path = os.path.normpath(os.path.join(base_playground_path, owner_username, project_name))
    
    if not os.path.abspath(owner_project_path).startswith(os.path.abspath(base_playground_path)):
        raise ValueError("Attempted path traversal detected.")
    
    lowerdir = owner_project_path
    
    contribution_id = uuid.uuid4().hex[:12]

    if not os.path.isdir(lowerdir):
        raise FileNotFoundError(f"Owner's project directory not found at: {lowerdir}")
     
    upperdir = os.path.join(base_playground_path, 'contributions', contribution_id, 'upper')
    os.makedirs(upperdir, exist_ok=True)
     
    workdir = os.path.join(base_playground_path, 'contributions', contribution_id, 'work')
    os.makedirs(workdir, exist_ok=True)

    new_contribution = Contribution(
        id=contribution_id,
        owner_directory_path=lowerdir,
        upperdir_path=upperdir,
        directory_id=directory.id
    )
    db.session.add(new_contribution)
    db.session.commit()
     
    container_name = f"contrib_{contributor_username}_for_{owner_username}_s_{project_name}_{contribution_id}"

    destination_path_in_container = f"/global/{owner_username}/{project_name}"
     
    mount_options = (
        f"type=overlay,destination={destination_path_in_container},"
        f"source=overlay,"# 'source' i s just a required placeholder for this mount type not something name
        f"overlay-options=lowerdir={lowerdir}:upperdir={upperdir}:workdir={workdir}"
    )
     
    command = [
        "docker", "run",
        "-d",           
        "--rm",         
        "--name", container_name,
        "--volume", f"{base_playground_path}:/playground:ro",
        "--mount", mount_options, # If knew beforehand would have saved 1hrs of work
        "-p", "7681",
        IMAGE_NAME
    ]
    # subprocess.run(command, check=True)

    # time.sleep(2)
     
    # result = subprocess.run(command, check=True, capture_output=True, text=True)
     
    #result = subprocess.run(["docker", "port", container_name, "7681", cont],                           capture_output=True, text=True,check=True)
    
    container_id = None

    try:
        print(f"Executing command: {' '.join(command)}")

        run_result = subprocess.run(command, check=True, capture_output=True, text=True)
        container_id = run_result.stdout.strip()
        print(f"Container '{container_name}' started successfully with ID : {container_id[:8]}")

        container = docker_client.containers.get(container_id)

        

        # output is like 0.0.0.0:6373
        host_port = container.attrs["NetworkSettings"]["Ports"]["7681/tcp"][0]["HostPort"]  #port_result.stdout.strip().split(":")[-1]


        if not host_port:
            raise RuntimeError("Failed to retrive host port for the container.")

        session_url = f"http://127.0.0.1:{host_port}"      

    # container_id = result.stdout.strip()

        container = docker_client.containers.get(container_id)

        track_session(container)
        print(f"Contributor container '{container_name}' started successfully.")
        return {"session_url": session_url, "contribution_id": contribution_id, "container_name": container_name}
    except subprocess.CalledProcessError as e:
        print(f" Error creating container session: {e.stderr}")

        db.session.rollback()
        contribution_to_delete = Contribution.query.get(contribution_id)
        if contribution_to_delete:
            db.session.delete(contribution_to_delete)
            db.session.commit()
        print("Something went wrong! I know very helpful you won't know unless you know technopathy git gud!!")
        return None
    except Exception as e:
        print(f"Something went wrong: {e}")

        if container_id:
            print(f"Cleaning up container '{container_name}' due to and error")
            container = docker_client.containers.get(container_id)
            container.stop(1)
        db.session.rollback()
        return None
    
    # host_port = result.stdout.strip().split(":")[-1]
    


def merge_contribution(owner_dir, contribution_upperdir):
    for item in os.listdir(contribution_upperdir):
        s = os.path.join(contribution_upperdir, item)
        d = os.path.join(owner_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    shutil.rmtree(contribution_upperdir)

def remove_contribution(contribution_upperdir):
    shutil.rmtree(contribution_upperdir)

# ------------ The garbage collector for idle containers -------------

def garbage_collector_dumb():
    with app.app_context():
        print(f"[{datetime.now()}] ---Running Garbage Collector")
        try:
            timeout_threshold = datetime.now(timezone.utc) - timedelta(seconds=SESSION_TTL_SECONDS)

            idle_sessions = ActiveSession.query.filter(ActiveSession.last_active < timeout_threshold).all()

            for session in idle_sessions:
                print(f"Session for container '{session.container_name}' is idle. Last active: {session.last_active}. Stopping.")
                try:
                    container = docker_client.containers.get(session.container_name)
                    container.stop(timeout=30) 
                    print(f"Container '{session.container_name}' stopped.")
                except docker.errors.NotFound:
                    print(f"Container '{session.container_name}' not found. It may have been stopped manually.")
                
                db.session.delete(session)
            db.session.commit()

        except Exception as e:
            print(f"Error during garbage collection run: {e}")
            db.session.rollback()

        # all_containers = docker_client.containers.list(filters={"status":"running"})
        # for cont in all_containers:
        #     is_app_container = cont.name.startswith(('lpine_session_','chaotic_guest','contrib_'))

        #     if not is_app_container:
        #         continue
        #     try:
        #         created_str = cont.attrs['Created']
        #         creation_time = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
        #         now = datetime.now(timezone.utc)
        #         age_seconds = (now - creation_time).total_seconds()

        #         if (age_seconds > SESSION_TTL_SECONDS):
        #             print(f"Container '{cont.name}' (age: {age_seconds:.0f}s) has exceeded TTL of {SESSION_TTL_SECONDS}s. Stopping.")
        #             cont.stop(timeout=30)
        #             print(f"{cont.name} have stopped!!")
    
def run_garbage_collector_periodically():
    while(True):
        garbage_collector_dumb()
        time.sleep(5 * 60)


## ========== FLASK PART ============== ##

# ---------merging contri route--------------- #

@app.route('/contributions/merge',methods=['POST'])
def merge_contribution_endpoints():
    data = request.get_json() or {}
    contribution_id = data.get('contribution_id')

    contribution = Contribution.query.filter_by(id=contribution_id).first() # Searching the db
    if not contribution:
        return jsonify({"error": "Contribution not found"}), 404
    
    owner_dir = contribution.owner_directory_path
    upperdir = contribution.upperdir_path

    merge_contribution(owner_dir, upperdir)

    db.session.delete(contribution)
    db.session.commit()

    return jsonify({"message":"contribution merged"}) 
    

#    owner_dir = data.get('owner_dir')
#    contribution_upperdir = data.get('contribution_upperdir')
#    merge_contribution(owner_dir=owner_dir, contribution_upperdir=contribution_upperdir)

# ------------- upstaging contri route-------------- # 

@app.route('/contributions/delete', methods=['DELETE'])
def remove_contribution_endpoints():
    data = request.get_json() or {}
    contribution_id = data.get('contribution_id')

    contribution = Contribution.query.filter_by(id=contribution_id).first() # Searching the db

    if not contribution:
        return jsonify({"error": "Contribution not found"}), 404
    
    upperdir = contribution.upperdir_path

    remove_contribution(upperdir)

    db.session.delete(contribution)
    db.session.commit()
    
    return({"message":"Contribution unstaged"})
    # remove_contribution(contribution_upperdir=contribution_upperdir)


# ------------ The heartbeat deamon ---------- #

@app.route('/session/heartbeat', methods=['POST'])
def session_heartbeat():
    data = request.get_json() or {}
    container_name = data.get('container_name')
    if not container_name:
        return jsonify({"error": "Container name is required"}), 400

    session = ActiveSession.query.filter_by(container_name=container_name).first()
    if session:
        session.last_active = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"message": "Heartbeat received"}), 200
    
    return jsonify({"error": "Active session not found"}), 404


# -------- just for status check --------- #

@app.route('/status')
def status():
    return jsonify({"status": "ok"})

# ------------ User add endpoint --------------- #

@app.route('/users',methods=['POST'])
def create_user():
    data = request.get_json() or {}
    username = data.get('username')
    if not username:
        return jsonify({"error": "Username is required"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error":"User already exist"}), 409
    
    new_user = User(username=username)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message":f"User {username} created"}), 201

# ------------ contri endpoint ---------------- #

@app.route('/contributions/<username>', methods=['GET'])
def get_contributions(username):
    user = User.query.filter_by(username=username).first()
    if not user: return jsonify({"error": "User not found"}), 404
    
    owned_dirs = Directory.query.filter_by(owner_id=user.id).all()
    contribs_data = []
    for directory in owned_dirs:
        for contrib in directory.contributions:
            contribs_data.append({
                "contribution_id": contrib.id,
                "project_path": directory.path
            })
    return jsonify(contribs_data)

# ------------directory endpoint ------------- #

@app.route('/directories/claim', methods=['POST'])
def claim_directory():
    data = request.get_json() or {}
    username = data.get('username')
    dir_path = data.get('path')

    if not username or not dir_path:
        return jsonify({"error":"Username and path are required"}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error":"User not found"}), 404
#-------------------------------------------------------------------    
    user_base = os.path.join(base_playground_path, username)
    os.makedirs(user_base, exist_ok=True)

    requested_path = os.path.normpath(os.path.join(user_base, dir_path.strip('/')))
    user_base_abspath = os.path.abspath(user_base)

    if not os.path.abspath(requested_path).startswith(user_base_abspath + os.sep) and os.path.abspath(requested_path) != user_base_abspath:
        return jsonify({"error": "Invalid path: outside your home directory"}), 403

    created_dir = False
    try:
        # Trying to create directory atomically like in dbms. If it already exists, FileExistsError is raised.
        os.mkdir(requested_path)
        created_dir = True
    except FileExistsError:
        # We'll still try to insert DB row and rely on Unix-deus.
        pass
    except OSError as e:
        # Some other filesystem error ( punishment from Unix-deus )
        return jsonify({"error": f"Filesystem error: {e}"}), 500
    try:
        new_dir = Directory(path=requested_path, owner_id=user.id)
        db.session.add(new_dir)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Someone else claimed it in the meantime. Late to party.
        if created_dir:
            try:
                # ensure directory empty before removing it (obviously duh)
                if not os.listdir(requested_path):
                    os.rmdir(requested_path)
            except Exception:
                # if cleanup fails, don't crash — leave the directory (if running, then leaving is correct choice)
                pass
        return jsonify({"error": "The directory is already claimed"}), 409
    except Exception as e:
        db.session.rollback()
        if created_dir:
            try:
                if not os.listdir(requested_path):
                    os.rmdir(requested_path)
            except Exception:
                pass
        return jsonify({"error": f"Database error: {str(e)}"}), 500

# --------- The permission part --------- #

    try:
        uid = pwd.getpwnam(username).pw_uid
        gid = grp.getgrnam(username).gr_gid
        os.chown(requested_path, uid, gid)
        os.chmod(requested_path, 0o700)
    except KeyError:
        pass
    except PermissionError:
        pass

    return jsonify({"message": f"Directory {dir_path} claimed by {username}"}), 201
    
    # full_path = os.path.join(base_playground_path, dir_path.strip('/'))
    # if Directory.query.filter_by(path=full_path).first():
    #     return jsonify({"error":"The directory is already claimed"}), 409
    
    # os.makedirs(full_path, exist_ok=True)
    # new_dir = Directory(path=full_path, owner_id=user.id)
    # db.session.add(new_dir)
    # db.session.commit()

    # return jsonify({"message": f"Directory {dir_path} claimed by {username}"}), 201
    
# ----------- session starter endpoint ------------ #

@app.route('/session', methods=['POST'])
def create_session(username = None):
    print("--- RUNNING THE LATEST VERSION OF THE CODE VERSION !>@ ---") 
    data = request.get_json() or {}
    is_guest = data.get('is_guest', False)

    try:
        if is_guest:
            session_url = create_guest_session()
            return jsonify({"message":"Guest session is ready","session_url":session_url})
        else:
            if username == None:
                username = data.get('username')
            target_path = data.get('path')

            if not username:
                return jsonify({"error": "Username is required for non-guest sessions"}), 400
            
            if not target_path:
                result = create_or_start_user_session(username)
                return jsonify(result)

            full_target_path = os.path.join(base_playground_path, target_path.strip('/'))
 
            if not os.path.abspath(full_target_path).startswith(base_playground_path):
                return jsonify({"error": "Invalid path specified"}), 400

            directory = Directory.query.filter_by(path=full_target_path).first()

            if not directory:
                result = create_guest_session()
                return jsonify(result)

            if directory.owner.username == username:
                result = create_or_start_user_session(username)
                return jsonify(result)
            else:
                # The user is a contributor
                owner_username = directory.owner.username
                project_name = os.path.basename(target_path)
                result = create_contributor_session(owner_username, username, project_name, directory)
                return jsonify(result)



            # print(f"Request received to start session for user: {username}")
            # session_url = create_or_start_user_session(username)
            # return jsonify({
            #     "message": f"Session for {username} is ready.",
            #     "session_url": session_url
            # })
    except Exception as e:
        return jsonify({"error": f"Failed to create session: {str(e)}"}), 500
    


    
# ---------------- file runner ----------------- #

if __name__ == '__main__':
    if not os.path.exists(base_playground_path):
        print(f"Creating base playground directory at: {base_playground_path}")
        os.makedirs(base_playground_path)
    with app.app_context():
        db.create_all()
    gc_thread = threading.Thread(target=run_garbage_collector_periodically, daemon=True)
    gc_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5000)