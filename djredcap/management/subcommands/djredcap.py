#!/usr/bin/python

import os
import csv
import json
import keyword
import sys
import re
import inflect
from django.core.management.base import BaseCommand, CommandError
	
header_keys = (
	'field_name',
	'form_name',
	'section_name',
	'field_type',
	'field_label',
	'choices',
	'field_note',
	'validation_type',
	'min_value',
	'max_value',
	'is_identifier',
	'branching_logic',
	'required',
	'custom_alignment',
	'question_number'
)

field_types = {
	'date_ymd': 'DateField',
	'number': 'FloatField',
	'integer': 'IntegerField',
	'email': 'EmailField',
	'text': 'CharField',
	'textarea': 'TextField',
	'calc': 'FloatField',
	'radio': 'CharField',
	'select': 'CharField',
	'checkbox': 'CharField',
	'yesno': 'BooleanField',
	'truefalse': 'BooleanField',
}

help = """Attempts to read a REDCap data dictionary (CSV) and output a matching JSON file.
Then attempts to read a JSON file and output matching Django models. Can take either a REDCap
CSV file or a json file as input."""
requires_model_validation = False;
db_module = 'django.db'
args = 'filename';

def csv2json(self, reader, fileName):
	"""
	Function that converts csv file to valid json. 
	"""
	newFileName = remove_file_extension(self,os.path.basename(fileName));
	fout = open(os.path.join(os.path.dirname(fileName),newFileName + '.json'), "w+");
	
	#repeating_rows is a group of repeating rows located within a form.
	#all_repeats is all of the repeating rows for that form.
	all_form_names = [];
	repeating_rows = [];
	all_repeats = [];
	form_list = [''];
	last_form_name = None;
	cur_depth = 0;
	json_str = '';
	
	#create record form
	recordDict = {};
	recordDict['form_name'] = 'Record';
	recordDict['section_name'] = 'Record';
	all_form_names.append(recordDict['form_name']);
	json_str = generate_json_form(self,recordDict);
	fout.write(json_str + '\n');
		
	json_str = '';

	for row in reader:
		if row['form_name']:
			#clean up form name
			row['form_name'] = form2model(self,row['form_name']);
			row['form_name'] = make_singular(self,row['form_name']);
			form_list[0] = row['form_name'];
			if row['form_name'] != last_form_name:
				new_form_name = row['form_name'] + ' 1~Record';
				if last_form_name:
					row['form_name']=check_duplicates(self,all_form_names,row['form_name']);
					all_form_names.append(row['form_name']);
					fout.write(json_str + '\n');
					if all_repeats:
						json_str=get_repeating_json_list(self,all_repeats,fout);
						print_repeats(self,json_str,fout);
					json_str = generate_json_form(self,row,new_form_name);
					all_repeats = [];
				elif last_form_name is None:
					json_str = generate_json_form(self,row,new_form_name);
				last_form_name = row['form_name'];
		"""
		Needed for special case csv's with repeats used, not needed otherwise.
		An array of rows is built depending on if that row has a startrepeat, endrepeat, or
		repeat in it. Every row between a startrepeat and endrepeat is added to the 
		array, while keeping track of the current depth of the array.

		An array might look like: [[-,-,-,[-,[-,-,-],-,[-,-,]]]], where each - is a 
		row and each list, besides the outermost one, is a group of rows inside a 
		startrepeat/endrepeat segment.
	
		The list is then scrubbed of empty indexs and rows with only endrepeat in the 
		field name. Relationships between forms (used for creating foreign keys) are
		made by appending the referenced form to the end of the field_name. 
		"""
		if row['field_name'].find('startrepeat') != -1:
			repeat_info = row['field_name'].strip().split();
			row['field_name'] = repeat_info[0];
			form_name = make_singular(self,form2model(self,'_'.join(repeat_info[3:])));
			form_name = check_duplicates(self,all_form_names,form_name);
		
			form_name = form_name + ' ' + repeat_info[2];

			form_list.append(form_name);
			all_form_names.append(form_name.split(' ')[0]);
					
			repeating_rows = last_inner_append(self,repeating_rows, [row],0,cur_depth);
			cur_depth = cur_depth + 1;
		elif row['field_name'].find('endrepeat') != -1:
			row['field_name'] = row['field_name'].strip().split()[0];
				
			repeating_rows = last_inner_append(self,repeating_rows, row,0,cur_depth);
			cur_depth = cur_depth - 1;
			repeating_rows = last_inner_append(self,repeating_rows,'',0,cur_depth);
		elif row['field_name'].find(' repeat ') != -1:
			repeat_info = row['field_name'].strip().split();
			row['field_name'] = repeat_info[0];
			form_name = make_singular(self,form2model(self,'_'.join(repeat_info[3:])));
			form_name = check_duplicates(self,all_form_names,form_name);
			
			form_name = form_name + ' ' + repeat_info[2];
			form_list.append(form_name);
			all_form_names.append(form_name.split(' ')[0]);

			repeating_rows = last_inner_append(self,repeating_rows, [row],0,cur_depth);
			cur_depth = cur_depth - 1;
			repeating_rows = last_inner_append(self,repeating_rows,'',0,cur_depth);
		elif len(repeating_rows) > 0:
			repeating_rows = last_inner_append(self,repeating_rows, row,0,cur_depth);
		if cur_depth <= 0 and len(repeating_rows) > 0:
			"""
			Run if there are values in the repeating_rows but the current depth
			is 0, meaning all startrepeats have been closed with endrepeats
			"""
			form_list[0] = form_list[0] + ' 1'
			repeating_rows = clean_list(self,repeating_rows);
			create_form_relations(self,repeating_rows,form_list,0,0);
			repeating_rows = order_list(self,repeating_rows);
			all_repeats.append(repeating_rows);
			repeating_rows = [];	
			form_list = [''];
			cur_depth = 0;
		elif cur_depth <= 0 and len(repeating_rows) == 0:
			#Print a row normally
			json_str = generate_json_field(self,row,json_str);
			cur_depth = 0;
			form_list = [''];
			repeating_rows = [];
		
	fout.write(json_str + '\n');
	if row['form_name'] != last_form_name:
		if last_form_name:
			json_str = generate_json_form(self,row);
			json_str = get_repeating_json_list(self,all_repeats, fout);
			print_repeats(self,json_str,fout);
			all_repeats = [];
	return fout.name;

def clean_list(self, repeats_list):
	"""
	Removes all values in a list that equal '' or 'endrepeat':
	If there are nested lists, it recursively calls itself to search those
	too.
	"""
	for j,item in reversed(list(enumerate(repeats_list))):
		if isinstance(item,list):
			item = clean_list(self,item);
		elif item == '':
			repeats_list.pop(j);
		elif item['field_name'] == 'endrepeat':
			repeats_list.pop(j);
	return repeats_list;

def create_form_relations(self, repeats_list, form_list, form_index, prev_form_index):
	"""
	Edit form names to include the previous form read, so models can reference
	each other through foreign keys. If there are nested lists, the function is 
	recursively called to search them too.
	"""
	num_lists = 0;
	for j, item in enumerate(repeats_list):
		if isinstance(item,list):
			num_lists = num_lists + 1;
			num_lists += create_form_relations(self,item, form_list, form_index+num_lists, form_index);
		else:
			item['form_name'] = form_list[form_index+num_lists] + '~' + form_list[prev_form_index];
	return num_lists;

def order_list(self, repeats_list):
	"""
	Given a list of repeating rows created in the csv2json function, this list will pull out all
	the embedded lists and order them in order of appearence, while keeping values in their
	correct list, even if they were seperated by another list.
	
	Ex: [a[b[c d]e]f] -> [[a f][b e][c d]]
	"""
	orderList = [[]];
	for j,item in enumerate(repeats_list):
		if isinstance(item,list):
			orderList.append(order_list(self,item));
		else:
			orderList[0].append(item);
	return orderList;		

def get_repeating_json_list(self, all_repeats, fout):
	"""
	Given a list of repeating fields from the csv file, this function
	will return a list of json forms generated from the repeating fields.
	"""
	json_str = '';
	all_json = [];
	for item in all_repeats:
		if isinstance(item,list):
			all_json.append(get_repeating_json_list(self,item,fout));
		else:
			if not json_str:
				json_str = generate_json_form(self,item);
			json_str = generate_json_field(self,item,json_str);
	all_json.append(json_str);
	return all_json;	
	
def print_repeats(self,json_repeating_rows,fout):
	"""
	json_repeating_rows is a list of lists with fields inside of 
	those lists.
	"""
	for item in json_repeating_rows:
		if isinstance(item,list):
			print_repeats(self,item,fout);
		else:
			if item != '':
				fout.write(item);
				fout.write('\n');

def print_list(self, someList, fout, json_str):
	"""
	Prints every value in someList, including values in nested lists
	"""
	for item in someList:
		if isinstance(item,list):
			print_list(self,item,fout,json_str);
		else:	
			json_str = generate_json_field(self,item,json_str);

def last_inner_append(self,x,y,curDepth,targetDepth):
	"""
	Finds the deepest index in a list of lists at a targetDepth.
	"""
	try:
		if(curDepth != targetDepth):
			if isinstance(x[-1],list):
				last_inner_append(self,x[-1],y,curDepth+1,targetDepth);
				return x;
	except IndexError:
		pass;
	x.append(y);
	return x;
		
def check_duplicates(self, form_names_list, form_name):
	"""
	Searches for duplicate form_names in form_names_list. If one is found
	a number(2) is appended to the end of form_name. If the new form_name is a 
	duplicate, the number at the end is incremented until no duplicates are
	found.
	"""
	for name in form_names_list:
		if name == form_name:
			endDigit = re.search('(\d+)$',form_name);
			if endDigit:
				endDigit = endDigit.start();
				form_name = list(form_name);
				form_name[endDigit:] = str(int("".join(form_name[endDigit:]))+1);
				form_name = "".join(form_name);
			else:
				form_name+=str(2);
			form_name = check_duplicates(self,form_names_list,form_name);
	return form_name	

def generate_json_form(self,row,form_name = None):
	if form_name:
		fname = form_name;
	else:
		fname = row['form_name'];
	return (json.dumps({	'form name': fname,
				'section header': row['section_name'],
				'fields': []},indent=0,separators=(',',': ')));

def generate_json_field(self, row, json_str):
	"""
	Generates the json for the given row. The json is formatted to 1 line for easier
	search when generating the django models.
	"""
	data = json.loads(str(json_str));
	if row:		
		data['fields'].append({
                                   'field name': row['field_name'],
                                   'field label': row['field_label'],
                                   'field note': row['field_note'],
                                   'field type': row['field_type'],
                                   'choices': row['choices'],
                                   'validation type': row['validation_type'],
                                   'min value': row['min_value'],
                                   'max value': row['max_value'],
                                   'identifier': row['is_identifier'],
                                   'branching logic': row['branching_logic'],
                                   'required': row['required'],
                                   'alignment': row['custom_alignment'],
                                   'question number': row['question_number'],
				})
	return json.dumps(data);

def json2dj(self, fileName):
	newFileName = remove_file_extension(self,os.path.basename(fileName));
	fout = open(os.path.join(os.path.dirname(fileName), 'models.py'), 'w+');

	fout.write('from %s import models' % self.db_module);
	fout.write('\n');
	
	fout.write('\n');	
	for line in open(fileName,'r'):
		field_num = 0;
		data = json.loads(line);
		form_name = data['form name'].replace('_','');
		fk_name = None;
			
		#extracting foreign key from form name
		if form_name.find('~') != -1:
                                form_name, fk_name = form_name.split('~');
				fk_name = fk_name.split(' ')[0].replace('_','');
				form_name = form_name.split(' ')[0].replace('_','');

		fout.write('class %s(models.Model):' % form_name);
                fout.write('\n');
		for field in data['fields']:
			extra_params = {};
			comment_notes = [];
			column_name,extra_params['verbose_name']=remove_string_formatting(self,field);	
			#column_name = get_field_value(self,field, 'field name');
			att_name = column_name.lower();

			#extra_params['verbose_name'] = get_field_value(self,field, 'field label');
			field['field note']=re.sub('$[A-Z]*[a-z]*','',field['field note'])
			extra_params['help_text']=get_field_value(self,field, 'field note');
			
			if ' ' in att_name or '-' in att_name or keyword.iskeyword(att_name) or column_name != att_name:
				extra_params['db_column'] = column_name;
			
			if ' ' in att_name:
				att_name = att_name.replace(' ','_');
				comment_notes.append('Field renamed to remove spaces.');
			if '-' in att_name:
				att_name = att_name.replace('-','_');
				comment_notes.append('Field renamed to remove dashes.');
			if att_name.endswith('_'):
				att_name = att_name[:-1];
				comment_notes.append('Field renamed to remove ending underscore');
			if column_name != att_name:
				comment_notes.append('Field name made lowercase.');
				
			field_type, field_params, field_notes = get_field_type(self,field);
			extra_params.update(field_params);
			comment_notes.extend(field_notes);
		
			field_type += '('

			if keyword.iskeyword(att_name):
				att_name += '_field';
				comment_notes.append('Field renamed because it was a Python reserved word.');
			if att_name[0].isdigit():
				att_name = 'number_%s' % att_name;
				extra_params['db_column'] = unicode(column_name);
				comment_notes.append("Field renamed because it wasn't a valid python identifier.");
		
			if att_name == 'id' and field_type == 'AutoField(' and extra_params == {'primary_key': True}:
				pass
			field_desc = '%s = models.%s' % (att_name, field_type);
			if extra_params:
				if not field_desc.endswith('('):
					field_desc += ', ';
				field_desc += ', '.join(['%s=%r' % (k, v) for k, v in extra_params.items()])
			field_desc += ')';
			if comment_notes:
				field_desc += ' # ' + ' '.join(comment_notes);
		
			fout.write('    %s\n' % field_desc);
		#final meta class
                if fk_name:
			fout.write(get_FK(self,fk_name));
                for meta_line in get_meta(self,form_name):
                        fout.write(meta_line);
def get_field_type(self, line):
	"""
	Given the database connection, the table name, and the cursor row description,
	this routine will return the given field type name, as well as any additional keyword
	parameters and notes for the field.
	"""
	field_params = {};
	field_notes = [];
	
	required = get_field_value(self,line,'required');
	validation_type = get_field_value(self,line,'validation type');
	field_type = get_field_value(self,line,'field type');

	try:
		field_type = field_types.get(validation_type, field_types[field_type]);
	except KeyError:
		field_type = 'TextField';
		field_notes.append('This field type is a guess');
	if not required:
		field_params['blank'] = True
		if field_type is 'BooleanField':
			field_type = 'NullBooleanField';
		else:
			field_params['null'] = True;
	if field_type == 'CharField':
		field_params['max_length'] = 2000;

	choices = None;
	if get_field_value(self,line,'choices'):
		try:
			choices = [(int(v.strip()), k.strip()) for v, k in [choice.split(',') \
				for choice in get_field_value(self,line,'choices').split('|')]]
			field_type = 'IntegerField'
		except (ValueError, TypeError):
			pass
		
	if choices:
		field_params['choices'] = choices;
	
	return field_type, field_params, field_notes;

def get_field_value(self, line, field):
	"""
	Determines the value of a field from the json representation.
	"""
	return str(line[field]);
	
def get_FK(self, form_name):
	"""
	Returns foreign key line needed in repeating models
	"""
	return '    ' + form_name.lower() + ' = models.ForeignKey(' + form_name + ')\n';

def get_meta(self, table_name):
	"""	
	Return a sequence comprising the lines of code necessary
	to construct the inner Meta class for the model 
	corresponding to the given database table name.
	"""
	table_name = str(table_name).lower();
	return ['\n',
		'    class Meta:\n',
		'	 db_table = %r\n' % table_name,
		'\n',
		'\n'];
	
def remove_file_extension(self,fileName):
	index = fileName.find('.');
	fileName = fileName[:index];
	return fileName;
	
def remove_string_formatting(self,line):
	"""
	Removes various junk from field_names and field_labels
	"""
	field_name = get_field_value(self,line,'field name');
	field_label = get_field_value(self,line,'field label');
	
	if field_name.find('$') != -1:
               	index = field_name.find('$');
               	field_name = field_name[:index] + field_name[index+4:];
        if field_label.find('$') != -1:
                field_label = re.sub(r'\$\w\d?\s','', field_label);
	if field_label.find('$placeholder') != -1:
		field_label = re.sub('\$placeholder','', field_label);
	return field_name,field_label;
		
def make_singular(self, field):
	p = inflect.engine();
	field_value = p.singular_noun(field);
	if field_value is False:
		return field;
	else:
		return field_value;
	
def form2model(self, form_name):
	"""
	Removes puncuation from form_name
	"""
	form_name = form_name.replace('-','').replace('/','').replace('(','').replace(')','');
	return form_name.title().replace(' ','');
