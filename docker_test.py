import docker
import time

IMAGE_NAME = "chaospine:1.0.0"
VOLUME_NAME = "test_user_home"
CONTAINER_NAME = "test_container_persistent"
TEST_FILE_PATH = "/root/persistence_test.txt"

client = docker.from_env()

def main():
    try:
        print(f">>> Starting container {CONTAINER_NAME} with volume {VOLUME_NAME}")
        container = client.containers.run(image=IMAGE_NAME,detach=True, name=CONTAINER_NAME, volumes={VOLUME_NAME:{'bind':'/root','mode':'rw'}}
        )

        print(f">>> container {container.short_id} started")
        time.sleep(2)

        print(f">>> writing a test file at {TEST_FILE_PATH}")

        exit_code, _ = container.exec_run(f"touch {TEST_FILE_PATH}")

        if exit_code != 0:
            raise Exception(">>> Failed to write on the given location")
        print(">>> File written successfully")

        print(f">>> Stopping the {container.short_id}...")
        container.stop()
        print(">>> Container Stopped")

        print(">>> Starting same container")
        container.start()
        print(f">>> Container started {container.short_id}...")

        time.sleep(2)

        print(f">>> checking if the file path exits {TEST_FILE_PATH}")

        run_code, output = container.exec_run(f"ls {TEST_FILE_PATH}")
        if run_code == 0:
            print(">>> Successfully persisted")
            print(output)
            print(f">>> Output is {output.decode().strip()}")
        else:
            raise Exception(">>> Path didn't persist")
    except Exception as e:
        print(f">>> An error occurred: {e}")
    
    finally:
        print(">>> Cleaning up")
        try:
            container_to_rem = client.containers.get(CONTAINER_NAME)
            container_to_rem.stop()
            container_to_rem.remove()
            print(f">>> Container '{CONTAINER_NAME}' removed.")
        except docker.errors.NotFound:
            print(f">>> Container '{CONTAINER_NAME}' was not running or found, skipping removal.")
        try:
            volume_to_remove = client.volumes.get(VOLUME_NAME)
            volume_to_remove.remove()
            print(f">>> Volume '{VOLUME_NAME}' removed.")
        except docker.errors.NotFound:
            print(f">>> Volume '{VOLUME_NAME}' not found.")
        
        print(">>> Cleanup complete.")

if __name__ == "__main__":
    main()