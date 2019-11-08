import os
import argparse

from m2a_process_helper import run


def generate_and_sync_env_report_file(env, region, report_path=os.getcwd()):

    try:
        if os.path.exists("{}/env_report/".format(report_path)):
            print("Deleting previous report files...")
            run.cmd("rm -rf {}/env_report/".format(report_path))

        print("Creating report file...")
        print("Running command: Scout2 --profile {} --regions {} --report-dir {}/env_report/ " \
              "--no-browser".format(env, region, report_path))

        run.cmd("Scout2 --profile {} --regions {} --report-dir {}/env_report/ --no-browser".format(env,
                                                                                                   region, report_path))

    except:
        print(("Error while producing report for {}".format(env)))
        pass

    try:
        print("Renaming report file...")
        run.cmd("mv {}/env_report/report-{}.html {}/env_report/report.html".format(report_path, env, report_path))

        print("Syncing report to s3://m2a-dashboard-{}-ui/public/report".format(env))
        run.cmd("aws --profile {} s3 sync {}/env_report/ s3://m2a-dashboard-{}-ui/public/report/".format(env, report_path, env))

        print("Deleting local report files...")
        run.cmd("rm -rf {}/env_report/".format(report_path))
    except:
        print("Error uploading report file {}".format(report_path))
        pass


def main():

    parser = argparse.ArgumentParser(description='Create and sync environment report')
    parser.add_argument('--env', '-e', help='Environment', required=True)
    parser.add_argument('--region', '-r', help='Region', required=True)
    parser.add_argument('--reportpath', '-rp', help='Path to the report', required=False)

    args = parser.parse_args()
    env = args.env
    region = args.region

    if args.reportpath:
        report_path = args.reportpath
    else:
        report_path = os.getcwd()

    generate_and_sync_env_report_file(env, region, report_path)

if __name__ == "__main__":
    main()
