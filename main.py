from python_terraform import *
import json
import os
import xlsxwriter
import argparse

def parse_var(s):
    items = s.split('=')
    key = items[0].strip()
    if len(items) > 1:
        value = '='.join(items[1:])
    return (key, value)


def parse_vars(items):
    d = {}

    if items:
        for item in items:
            key, value = parse_var(item)
            d[key] = value
    return d

def ofname(tfpath=".",extension=".xlsx"):
    os.chdir(tfpath)
    str1=os.getcwd()
    str2=str1.split('/')
    n=len(str2)
    name = str2[n-1] + extension
    return name

def flattener(jdata,row,column,worksheet,itemc):
    # print("Row:"+str(row)+"\nColumn:"+str(column)+"\nCount:"+str(itemc)+"\nData:"+json.dumps(jdata)+"\n")
    if isinstance(jdata,dict):
        for k,v in jdata.items():
            if isinstance(v,dict) or isinstance(v,list):
                # print(k)
                worksheet.write(row,column,k)
                if isinstance(v,list) and len(v) == 1 :
                    row = flattener(v[0],row,column+1,worksheet,len(v))
                else:
                    row = flattener(v,row,column+1,worksheet,len(v))
                # print("ROW: "+str(row))
                # print("COLUMN: "+str(column))
            else:
                # print(k+":"+str(v))
                worksheet.write(row,column,k)
                worksheet.write(row,column+1,v)
                row = row + 1
    else:
        for v in jdata:
            if isinstance(v,dict) or isinstance(v,list):
                row = flattener(v,row,column,worksheet,len(v))
                # print("ROW: "+str(row))
                # print("COLUMN: "+str(column))
            else:
                # print(v)
                worksheet.write(row,column,v)
                row = row + 1
    # print("\n")
    return row

vars = {}
parser = argparse.ArgumentParser(description="...")
parser.add_argument("--set",
                        metavar="KEY=VALUE",
                        nargs='+')
parser.add_argument("--tfpath",
                    type=str,
                    required=True)
args = parser.parse_args()
vars = parse_vars(args.set)

tfpath = args.tfpath

tf = Terraform(working_dir=tfpath)
tf.init()
tf.plan(out="plan.tfplan",var=vars)
json_data = tf.show("plan.tfplan",json=IsFlagged)

plan = json.loads(json_data[1])

classed = {}

for rc in plan['resource_changes']:
    classed[rc["type"]] = {}

for rc in plan['resource_changes']:
    rc_dict = rc['change']['after']
    rc_dict['address'] = rc['address']
    rc_dict['type'] = rc['type']
    classed[rc["type"]].update({rc['address']: rc_dict})

workbook = xlsxwriter.Workbook(ofname(tfpath))
cell_format = workbook.add_format()
cell_format.set_text_wrap()
cell_format.set_align("vcenter")
for type,data in classed.items():
    sheet = type[:31]
    worksheet = workbook.add_worksheet(sheet)
    worksheet.set_column(0,1000,42,cell_format)
    flattener(data,1,0,worksheet,0)
workbook.close()

# os.system("tfcheck")
os.system("rm plan.tfplan")