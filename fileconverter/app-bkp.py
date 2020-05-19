import os
from flask import Flask, request, redirect, render_template
from werkzeug.utils import secure_filename
import xlrd
import csv
import subprocess
import base64
from constants import ALLOWED_EXTENSIONS, XLSX_TYPE, CSV_TYPE

UPLOAD_FOLDER = os.path.dirname(os.path.abspath(__file__)) + '/uploads/'
DOWNLOAD_FOLDER = os.path.dirname("/var/lib/awx/projects/HealthCheck-Dailyinside/")
DOWNLOAD_FOLDER_ADHOC = os.path.dirname("/var/lib/awx/projects/HealthCheck-Adhoc/")

app = Flask(__name__, static_url_path="/static")
DIR_PATH = os.path.dirname(os.path.realpath(__file__))

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_type(filename):
    if '.' in filename and filename.rsplit('.', 1)[1].lower() == XLSX_TYPE:
        return XLSX_TYPE
    else:
        return CSV_TYPE


def check_adhoc_file(filename):
    if "adhoc" in filename:
        return True


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            print('No file attached in request')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            print('No file selected')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            process_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), filename)
    return render_template('index.html')


def process_file(path, filename):
    file_type = get_file_type(filename)
    is_adhoc_file = check_adhoc_file(filename)
    if file_type == XLSX_TYPE:
        convert_file_to_inventory(path, is_adhoc_file)
    else:
        convert_csv_to_inventory(path, is_adhoc_file)
    execute_command(is_adhoc_file)


def convert_file_to_inventory(import_file_path, is_adhoc_file):
    workbook = xlrd.open_workbook(import_file_path)
    sh = workbook.sheet_by_name("Sheet1")
    non_cluster = []
    clusters = []

    for n in range(sh.nrows):
        data = sh.row_values(n)
        if n != 0 and n <= sh.nrows - 1 and len(data[0].strip()) != 0:
            if "/" in data[1]:
                ip_addresses = data[1].split("/")
                if ip_addresses:
                    for count, ip_address in enumerate(ip_addresses):
                        if data[7].lower() == "no":
                            non_cluster.append({"ansible_ipaddress": ip_address.strip(), "ansible_host_name": data[0],
                                                "ansible_connection": data[2], "ansible_user": data[3],
                                                "ansible_ssh_pass": data[4], "ansible_application": data[5],
                                                "ansible_business": data[6], "ansible_cluster": data[7]})
                        else:
                            clusters.append({"ansible_ipaddress": ip_address.strip(), "ansible_host_name": data[0],
                                             "ansible_connection": data[2], "ansible_user": data[3],
                                             "ansible_ssh_pass": data[4], "ansible_application": data[5],
                                             "ansible_business": data[6], "ansible_cluster": data[7]})
            else:
                if data[7].lower() == "no":
                    non_cluster.append({"ansible_ipaddress": data[1].strip(), "ansible_host_name": data[0],
                                        "ansible_connection": data[2], "ansible_user": data[3],
                                        "ansible_ssh_pass": data[4], "ansible_application": data[5],
                                        "ansible_business": data[6], "ansible_cluster": data[7]})
                else:
                    clusters.append({"ansible_ipaddress": data[1].strip(), "ansible_host_name": data[0],
                                     "ansible_connection": data[2], "ansible_user": data[3],
                                     "ansible_ssh_pass": data[4], "ansible_application": data[5],
                                     "ansible_business": data[6], "ansible_cluster": data[7]})

    write_to_file(non_cluster, clusters, is_adhoc_file)


def write_to_file(non_cluster, clusters, is_adhoc_file):
    if is_adhoc_file:
        filepath = os.path.join(DOWNLOAD_FOLDER_ADHOC + "/hosts")
        file = open(filepath, "w")
    else:
        filepath = os.path.join(DOWNLOAD_FOLDER + "/hosts")
        file = open(filepath, "w")

    file.write("[non-cluster]")
    file.write("\n")
    for cluster in non_cluster:
        file.write(cluster["ansible_ipaddress"].strip() + " ")
        file.write("ansible_host_name=" + cluster["ansible_host_name"] + " ")
        file.write("ansible_connection=" + cluster["ansible_connection"] + " ")
        file.write("ansible_user=" + cluster["ansible_user"] + " ")
        file.write("ansible_ssh_pass=" + password_decoder(cluster["ansible_ssh_pass"]).strip() + " ")
        file.write("ansible_application=" + cluster["ansible_application"].replace(" ", "_") + " ")
        file.write("ansible_business=" + cluster["ansible_business"].replace(" ", "_") + " ")
        if cluster["ansible_cluster"].lower() == "no":
            file.write("ansible_cluster=false\n")

    file.write("\n")
    file.write("[cluster]")
    file.write("\n")
    for cluster in clusters:
        file.write(cluster["ansible_ipaddress"].strip() + " ")
        file.write("ansible_host_name=" + cluster["ansible_host_name"] + " ")
        file.write("ansible_connection=" + cluster["ansible_connection"] + " ")
        file.write("ansible_user=" + cluster["ansible_user"] + " ")
        file.write("ansible_ssh_pass=" + password_decoder(cluster["ansible_ssh_pass"]).strip() + " ")
        file.write("ansible_application=" + cluster["ansible_application"].replace(" ", "_") + " ")
        file.write("ansible_business=" + cluster["ansible_business"].replace(" ", "_") + " ")
        if cluster["ansible_cluster"].lower() == "yes":
            file.write("ansible_cluster=true\n")

    file.write("\n")
    file.write("[cluster:vars]")
    file.write("\n")
    file.write("ansible_cluster=true")
    file.write("\n")
    file.write("\n")
    file.write("[non-cluster:vars]")
    file.write("\n")
    file.write("ansible_cluster=false")


def convert_csv_to_inventory(import_file_path, is_adhoc_file):
    with open(import_file_path) as csv_file:
        non_cluster = []
        clusters = []
        csv_reader = csv.reader(csv_file, delimiter=',')
        for n, row in enumerate(csv_reader):
            if n != 0:
                if "/" in row[1]:
                    ip_addresses = row[1].split("/")
                    if ip_addresses:
                        for count, ip_address in enumerate(ip_addresses):
                            if row[7].lower() == "no":
                                non_cluster.append({"ansible_ipaddress": ip_address.strip(), "ansible_host_name": row[0],
                                                    "ansible_connection": row[2], "ansible_user": row[3],
                                                    "ansible_ssh_pass": row[4], "ansible_application": row[5],
                                                    "ansible_business": row[6], "ansible_cluster": row[7]})
                            else:
                                clusters.append({"ansible_ipaddress": ip_address.strip(), "ansible_host_name": row[0],
                                                 "ansible_connection": row[2], "ansible_user": row[3],
                                                 "ansible_ssh_pass": row[4], "ansible_application": row[5],
                                                 "ansible_business": row[6], "ansible_cluster": row[7]})
                else:
                    if row[7].lower() == "no":
                        non_cluster.append({"ansible_ipaddress": row[1].strip(), "ansible_host_name": row[0],
                                            "ansible_connection": row[2], "ansible_user": row[3],
                                            "ansible_ssh_pass": row[4], "ansible_application": row[5],
                                            "ansible_business": row[6], "ansible_cluster": row[7]})
                    else:
                        clusters.append({"ansible_ipaddress": row.strip(), "ansible_host_name": row[0],
                                         "ansible_connection": row[2], "ansible_user": row[3],
                                         "ansible_ssh_pass": row[4], "ansible_application": row[5],
                                         "ansible_business": row[6], "ansible_cluster": row[7]})
    write_to_file(non_cluster, clusters, is_adhoc_file)


def password_decoder(ssh_pass):
    base64_pass = ssh_pass
    base64_bytes = base64_pass.encode('ascii')
    pass_bytes = base64.b64decode(base64_bytes)
    ssh_pass = pass_bytes.decode('ascii')
    return ssh_pass


def execute_command(is_adhoc_file):
    try:
        if is_adhoc_file:
            subprocess.call(
                "awx-manage inventory_import --inventory-name DailyInventory --source "
                + DOWNLOAD_FOLDER_ADHOC + "/hosts --overwrite", shell=True)
        else:
            subprocess.call(
                "awx-manage inventory_import --inventory-name DailyInventory --source "
                + DOWNLOAD_FOLDER + "/hosts --overwrite", shell=True)
    except Exception as e:
        print("awx-manage command fail reason: %s" % e.message)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='192.168.0.104', port=port)
