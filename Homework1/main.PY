import os

print(os.getpid())

print(os.getppid())

for key, value in os.environ.items():
    print(f"{key}: {value}")

print(os.listdir("/proc/self/fd"))

if __name__ == "__main__":
    print("This script is being run directly.")