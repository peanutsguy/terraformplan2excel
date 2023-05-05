Recently, I was working with an Azure design for a customer, and I needed to compare what my terraform scripts had planned for against my customer's Excel template.

If we were talking about a few resources with static names and properties, it wouldn't be too hard to comb through the terraform scripts and compare them against the Excel template. However, the customer's design had about 60+ resources, distributed in 15 Resource Groups.

So, I decided to do everything harder (now) so that it was easier (later), and started writing a Python script that would create a Terraform Plan, parse it and then generate an Excel file with all the resources grouped by type in different worksheets.

## Terraform Prep

First of all, since my customer was using Azure as the Terraform backend and deploying via Azure DevOps agent, I had to do some prepping in the form of a [Terraform override file](https://developer.hashicorp.com/terraform/language/files/override) so that I could execute my plan locally and get a full rundown as if there were no deployed resources.

Since it was mainly backend and provider, what I had to override, I named my file `backend_override.tf`, which I placed in the same folder where the rest of my Terraform scripts were.

The file ended looking something like this:
```
terraform {
  backend "local" {
    path = "./.local-state"
  }
}

provider "azurerm" {
  features {}
  client_id       = "00000000-0000-0000-0000-000000000000"
  client_secret   = "MySuperSecretPassword"
  tenant_id       = "10000000-0000-0000-0000-000000000000"
  subscription_id = "20000000-0000-0000-0000-000000000000"
}
```

## Python Script

The script has two main parts:
 - Terraform planning
 - Plan flattener and Excel file creation

### Parsing arguments

First, I had to write the base for the script. The script would receive a couple of arguments:

| Argument | Description | Optional | Example |
|:-:|-|:-:|-|
| `--tfpath` | The path to the folder that contains the terraform files | `false` | `--tfpath "terraform/"` |
| `--set` | The variables that would normally be passed via command line o additional `tfvars` files | `true` | `--set location="Central US" testing=true ` |

This arguments are parsed using `argparse` and saving the Terraform path to `tfpath` and the variables as a `dict` in `vars`.
> I based this part on Sam Starkman's [article](https://towardsdatascience.com/a-simple-guide-to-command-line-arguments-with-argparse-6824c30ab1c3) and Laurent Franceschetti's [gist](https://gist.github.com/fralau/061a4f6c13251367ef1d9a9a99fb3e8d)

```python
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
```

### Executing Terraform

To execute Terraform, I used the [`python_terraform`](https://github.com/beelit94/python-terraform/blob/master/README.md) library. I generated the plan, passing `vars` as an argument value for `var`, saved it first to `plan.tfplan` and the read it as a JSON into the variable `plan`. The code to generate the Terraform plan is really simple:

```python
from python_terraform import *
import json

tf = Terraform(working_dir=tfpath)
tf.init()
tf.plan(out="plan.tfplan",var=vars)
json_data = tf.show("plan.tfplan",json=IsFlagged)

plan = json.loads(json_data[1])
```

### Parsing the Terraform plan

Finally, I needed to parse the plan, especifically `resource_changes`. Since it contained everything from `null` and `false`, all the way to `list` and `dict` values, I decided to do a recursive function (`flattener`) that would iterate through all the resources.

> The bit where I get the current directory, for the Excel file name, is based on [vinithravit's answer](https://stackoverflow.com/a/10293159) over at StackOverflow.

```python
import json
import xlsxwriter

def ofname(tfpath=".",extension=".xlsx"):
    os.chdir(tfpath)
    str1=os.getcwd()
    str2=str1.split('/')
    n=len(str2)
    name = str2[n-1] + extension
    return name

def flattener(jdata,row,column,worksheet,itemc):
    if isinstance(jdata,dict):
        for k,v in jdata.items():
            if isinstance(v,dict) or isinstance(v,list):
                worksheet.write(row,column,k)
                if isinstance(v,list) and len(v) == 1 :
                    row = flattener(v[0],row,column+1,worksheet,len(v))
                else:
                    row = flattener(v,row,column+1,worksheet,len(v))
            else:
                worksheet.write(row,column,k)
                worksheet.write(row,column+1,v)
                row = row + 1
    else:
        for v in jdata:
            if isinstance(v,dict) or isinstance(v,list):
                row = flattener(v,row,column,worksheet,len(v))
            else:
                worksheet.write(row,column,v)
                row = row + 1
    return row

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
```

### Final Script

Putting everything together, plus a couple of minor adjustments (like the addition of `tfcheck` [a small bash script that I wrote to validate Terraform scripts] and `rm plan.tfplan` for cleaning up), the script ends up as follows:

```python
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
    if isinstance(jdata,dict):
        for k,v in jdata.items():
            if isinstance(v,dict) or isinstance(v,list):
                worksheet.write(row,column,k)
                if isinstance(v,list) and len(v) == 1 :
                    row = flattener(v[0],row,column+1,worksheet,len(v))
                else:
                    row = flattener(v,row,column+1,worksheet,len(v))
            else:
                worksheet.write(row,column,k)
                worksheet.write(row,column+1,v)
                row = row + 1
    else:
        for v in jdata:
            if isinstance(v,dict) or isinstance(v,list):
                row = flattener(v,row,column,worksheet,len(v))
            else:
                worksheet.write(row,column,v)
                row = row + 1
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

os.system("tfcheck")
os.system("rm plan.tfplan")
```

I'm no Python expert, by any means, and I'm sure that this script can be improved and optimized.

## Usage

Now, how do we use this script? Pretty easily. Once we've created our override file for Terraform, we simply run the script, passing the arguments we require:

```bash
python3 main.py --tfpath terraform/ --set location="Central US" testing=true
```