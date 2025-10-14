# The cursed bloodbath of trying to make shared editing enviroment maybe too cursed to be used haha
import uuid
import os
import subprocess

lowerdir = f'/global/{owner_username}'
KEY_A = uuid.uuid4().hex[:8]
KEY_B = uuid.uuid4().hex[:8]
KEY_C = uuid.uuid4().hex[:8]

upperdir = f'/global/contribution/{KEY_A}'
workdir = f'/global/contribution/{KEY_B}'
merged = f'/global/contribution/{KEY_C}'

# The symlink connection for owner
upperdir_owner = f'/global/{owner_username}/{KEY_A}'
workdir_owner = f'global/{owner_username}/{KEY_B}'
merged_owner = f'global/{owner_username}/{KEY_C}'

# The symlink connection for contributor
upperdir_contributor = f'/global/{contributor_username}/{KEY_A}'
workdir_contributor = f'/global/{contributor_username}/{KEY_B}'
merged_contributor = f'/global/{contributor_username}/{KEY_C}'

for d in [upperdir, workdir, merged, upperdir_owner, workdir_owner, merged_owner,upperdir_contributor, workdir_contributor, merged_contributor]:
    os.makedirs(d,exist_ok=True)

# Make connection across global
command_ln1 =f'ln -s upperdir upperdir_owner upperdir_contributor'
command_ln1 = 'ln -s workdir workdir_owner workdir_contributor'
command_ln1= 'ln -s merged merged_owner merged_contributor' 
            
subprocess.run(command_ln, shell=True)

command_d = f""" 
            docker run -it --rm --privileged {IMAGE_NAME} bash -c "
            mount -t overlay overlay -o lowerdir={lowerdir}, upperdir={upperdir},workdir={workdir} {merged} && bash
            "
            """ 
subprocess.run(command_d,shell=True)