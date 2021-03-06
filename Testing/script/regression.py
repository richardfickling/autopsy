#!/usr/bin/python 
#en_US.latin-1
import codecs
import datetime
import logging
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from sys import platform as _platform
import time
import traceback
import xml
from xml.dom.minidom import parse, parseString

#
# Please read me...
#
# This is the regression testing Python script.
# It uses an ant command to run build.xml for RegressionTest.java
#
# The code is cleanly sectioned and commented.
# Please follow the current formatting.
# It is a long and potentially confusing script.
#
# Variable, function, and class names are written in Python conventions:
# this_is_a_variable    this_is_a_function()    ThisIsAClass
#
# All variables that are needed throughout the script have been initialized
# in a global class.
# - Command line arguments are in Args (named args)
# - Information pertaining to each test is in TestAutopsy (named case)
# - Queried information from the databases is in Database (named database)
# Feel free to add additional global classes or add to the existing ones,
# but do not overwrite any existing variables as they are used frequently.
#



#-------------------------------------------------------------#
# Parses argv and stores booleans to match command line input #
#-------------------------------------------------------------#
class Args:
    def __init__(self):
        self.single = False
        self.single_file = ""
        self.rebuild = False
        self.list = False
        self.config_file = ""
        self.unallocated = False
        self.ignore = False
        self.keep = False
        self.verbose = False
        self.exception = False
        self.exception_string = ""
    
    def parse(self):
        sys.argv.pop(0)
        while sys.argv:
            arg = sys.argv.pop(0)
            if(arg == "-f"):
                try:
                    arg = sys.argv.pop(0)
                    printout("Running on a single file:")
                    printout(path_fix(arg) + "\n")
                    self.single = True
                    self.single_file = path_fix(arg)
                except:
                    printerror("Error: No single file given.\n")
                    return False
            elif(arg == "-r" or arg == "--rebuild"):
                printout("Running in rebuild mode.\n")
                self.rebuild = True
            elif(arg == "-l" or arg == "--list"):
                try:
                    arg = sys.argv.pop(0)
                    printout("Running from configuration file:")
                    printout(arg + "\n")
                    self.list = True
                    self.config_file = arg
                except:
                    printerror("Error: No configuration file given.\n")
                    return False
            elif(arg == "-u" or arg == "--unallocated"):
               printout("Ignoring unallocated space.\n")
               self.unallocated = True
            elif(arg == "-i" or arg == "--ignore"):
                printout("Ignoring the ./input directory.\n")
                self.ignore = True
            elif(arg == "-k" or arg == "--keep"):
                printout("Keeping the Solr index.\n")
                self.keep = True
            elif(arg == "-v" or arg == "--verbose"):
                printout("Running in verbose mode:")
                printout("Printing all thrown exceptions.\n")
                self.verbose = True
            elif(arg == "-e" or arg == "--exception"):
                try:
                    arg = sys.argv.pop(0)
                    printout("Running in exception mode: ")
                    printout("Printing all exceptions with the string '" + arg + "'\n")
                    self.exception = True
                    self.exception_string = arg
                except:
                    printerror("Error: No exception string given.")
            elif arg == "-h" or arg == "--help":
                printout(usage())
                return False
            else:
                printout(usage())
                return False
        # Return the args were sucessfully parsed
        return True



#-----------------------------------------------------#
# Holds all global variables for each individual test #
#-----------------------------------------------------#
class TestAutopsy:
    def __init__(self):
        # Paths:
        self.input_dir = make_local_path("input")
        self.output_dir = ""
        self.gold = "gold"
        # Logs:
        self.antlog_dir = ""
        self.common_log = ""
        self.csv = ""
        self.global_csv = ""
        self.html_log = ""
        # Error tracking
        self.printerror = []
        self.printout = []
        self.report_passed = False
        # Image info:
        self.image_file = ""
        self.image_name = ""
        # Ant info:
        self.known_bad_path = ""
        self.keyword_path = ""
        self.nsrl_path = ""
        # Case info
        self.start_date = ""
        self.end_date = ""
        self.total_test_time = ""
        self.total_ingest_time = ""
        self.autopsy_version = ""
        self.heap_space = ""
        self.service_times = ""
        self.ingest_messages = 0
        self.indexed_files = 0
        self.indexed_chunks = 0
        
        # Set the timeout to something huge
        # The entire tester should not timeout before this number in ms
        # However it only seems to take about half this time
        # And it's very buggy, so we're being careful
        self.timeout = 24 * 60 * 60 * 1000 * 1000
        self.ant = []
      
    def get_image_name(self, image_file):
        path_end = image_file.rfind("/")
        path_end2 = image_file.rfind("\\")
        ext_start = image_file.rfind(".")
        if(ext_start == -1):
            name = image_file
        if(path_end2 != -1):
            name = image_file[path_end2+1:ext_start]
        elif(ext_start == -1):
            name = image_file[path_end+1:]
        elif(path_end == -1):
            name = image_file[:ext_start]
        elif(path_end!=-1 and ext_start!=-1):
            name = image_file[path_end+1:ext_start]
        else:
            name = image_file[path_end2+1:ext_start]
        return name
        
    def ant_to_string(self):
        string = ""
        for arg in self.ant:
            string += (arg + " ")
        return string
        
    def reset(self):
        # Logs:
        self.antlog_dir = ""
        # Error tracking
        self.printerror = []
        self.printout = []
        self.report_passed = False
        # Image info:
        self.image_file = ""
        self.image_name = ""
        # Ant info:
        self.known_bad_path = ""
        self.keyword_path = ""
        self.nsrl_path = ""
        # Case info
        self.start_date = ""
        self.end_date = ""
        self.total_test_time = ""
        self.total_ingest_time = ""
        self.heap_space = ""
        self.service_times = ""
        
        # Set the timeout to something huge
        # The entire tester should not timeout before this number in ms
        # However it only seems to take about half this time
        # And it's very buggy, so we're being careful
        self.timeout = 24 * 60 * 60 * 1000 * 1000
        self.ant = []



#---------------------------------------------------------#
# Holds all database information from querying autopsy.db #
#  and standard.db. Initialized when the autopsy.db file  #
#          is compared to the gold standard.              #
#---------------------------------------------------------#
class Database:
    def __init__(self):
        self.gold_artifacts = []
        self.autopsy_artifacts = []
        self.gold_attributes = 0
        self.autopsy_attributes = 0
        self.gold_objects = 0
        self.autopsy_objects = 0
        self.artifact_comparison = []
        self.attribute_comparison = []
        
    def clear(self):
        self.gold_artifacts = []
        self.autopsy_artifacts = []
        self.gold_attributes = 0
        self.autopsy_attributes = 0
        self.gold_objects = 0
        self.autopsy_objects = 0
        self.artifact_comparison = []
        self.attribute_comparison = []
        
    def get_artifacts_count(self):
        total = 0
        for nums in self.autopsy_artifacts:
            total += nums
        return total
        
    def get_artifact_comparison(self):
        if not self.artifact_comparison:
            return "All counts matched"
        else:
            return "; ".join(self.artifact_comparison)
        
    def get_attribute_comparison(self):
        if not self.attribute_comparison:
            return "All counts matched"
        list = []
        for error in self.attribute_comparison:
            list.append(error)
        return ";".join(list)
        
    def generate_autopsy_artifacts(self):
        if not self.autopsy_artifacts:
            autopsy_db_file = os.path.join("./", case.output_dir, case.image_name,
                                          "AutopsyTestCase", "autopsy.db")
            autopsy_con = sqlite3.connect(autopsy_db_file)
            autopsy_cur = autopsy_con.cursor()
            autopsy_cur.execute("SELECT COUNT(*) FROM blackboard_artifact_types")
            length = autopsy_cur.fetchone()[0] + 1
            for type_id in range(1, length):
                autopsy_cur.execute("SELECT COUNT(*) FROM blackboard_artifacts WHERE artifact_type_id=%d" % type_id)
                self.autopsy_artifacts.append(autopsy_cur.fetchone()[0])
                
    def generate_autopsy_attributes(self):
        if self.autopsy_attributes == 0:
            autopsy_db_file = os.path.join("./", case.output_dir, case.image_name,
                                          "AutopsyTestCase", "autopsy.db")
            autopsy_con = sqlite3.connect(autopsy_db_file)
            autopsy_cur = autopsy_con.cursor()
            autopsy_cur.execute("SELECT COUNT(*) FROM blackboard_attributes")
            autopsy_attributes = autopsy_cur.fetchone()[0]
            self.autopsy_attributes = autopsy_attributes

    def generate_autopsy_objects(self):
        if self.autopsy_objects == 0:
            autopsy_db_file = os.path.join("./", case.output_dir, case.image_name,
                                          "AutopsyTestCase", "autopsy.db")
            autopsy_con = sqlite3.connect(autopsy_db_file)
            autopsy_cur = autopsy_con.cursor()
            autopsy_cur.execute("SELECT COUNT(*) FROM tsk_objects")
            autopsy_objects = autopsy_cur.fetchone()[0]
            self.autopsy_objects = autopsy_objects
        
    def generate_gold_artifacts(self):
        if not self.gold_artifacts:
            gold_db_file = os.path.join("./", case.gold, case.image_name, "standard.db")
            gold_con = sqlite3.connect(gold_db_file)
            gold_cur = gold_con.cursor()
            gold_cur.execute("SELECT COUNT(*) FROM blackboard_artifact_types")
            length = gold_cur.fetchone()[0] + 1
            for type_id in range(1, length):
                gold_cur.execute("SELECT COUNT(*) FROM blackboard_artifacts WHERE artifact_type_id=%d" % type_id)
                self.gold_artifacts.append(gold_cur.fetchone()[0])
                
    def generate_gold_attributes(self):
        if self.gold_attributes == 0:
            gold_db_file = os.path.join("./", case.gold, case.image_name, "standard.db")
            gold_con = sqlite3.connect(gold_db_file)
            gold_cur = gold_con.cursor()
            gold_cur.execute("SELECT COUNT(*) FROM blackboard_attributes")
            self.gold_attributes = gold_cur.fetchone()[0]

    def generate_gold_objects(self):
        if self.gold_objects == 0:
            gold_db_file = os.path.join("./", case.gold, case.image_name, "standard.db")
            gold_con = sqlite3.connect(gold_db_file)
            gold_cur = gold_con.cursor()
            gold_cur.execute("SELECT COUNT(*) FROM tsk_objects")
            self.gold_objects = gold_cur.fetchone()[0]



#----------------------------------#
#      Main testing functions      #
#----------------------------------#

# Iterates through an XML configuration file to find all given elements        
def run_config_test(config_file):
    try:
        parsed = parse(config_file)
        if parsed.getElementsByTagName("indir"):
            case.input_dir = parsed.getElementsByTagName("indir")[0].getAttribute("value").encode().decode("utf-8")
        if parsed.getElementsByTagName("global_csv"):
            case.global_csv = parsed.getElementsByTagName("global_csv")[0].getAttribute("value").encode().decode("utf-8")
        
        # Generate the top navbar of the HTML for easy access to all images
        values = []
        for element in parsed.getElementsByTagName("image"):
            value = element.getAttribute("value").encode().decode("utf-8")
            if file_exists(value):
                values.append(value)
        html_add_images(values)
        
        # Run the test for each file in the configuration
        for element in parsed.getElementsByTagName("image"):
            value = element.getAttribute("value").encode().decode("utf-8")
            if file_exists(value):
                run_test(value)
            else:
                printerror("Warning: Image file listed in the configuration does not exist:")
                printerror(value + "\n")
    except Exception as e:
        printerror("Error: There was an error running with the configuration file.")
        printerror(str(e) + "\n")
        logging.critical(traceback.format_exc())

# Runs the test on the single given file.
# The path must be guarenteed to be a correct path.
def run_test(image_file):
    if not image_type(image_file) != IMGTYPE.UNKNOWN:
        printerror("Error: Image type is unrecognized:")
        printerror(image_file + "\n")
        return
        
    # Set the case to work for this test
    case.image_file = image_file
    case.image_name = case.get_image_name(image_file)
    case.antlog_dir = make_local_path(case.output_dir, case.image_name, "antlog.txt")
    case.known_bad_path = make_path(case.input_dir, "notablehashes.txt-md5.idx")
    case.keyword_path = make_path(case.input_dir, "notablekeywords.xml")
    case.nsrl_path = make_path(case.input_dir, "nsrl.txt-md5.idx")
    
    logging.debug("--------------------")
    logging.debug(case.image_name)
    logging.debug("--------------------")
    
    run_ant()
    time.sleep(2) # Give everything a second to process
    
    # After the java has ran:
    copy_logs()
    generate_common_log()
    try:
        fill_case_data()
    except Exception as e:
        printerror("Error: Unknown fatal error when filling case data.")
        printerror(str(e) + "\n")
        logging.critical(traceback.format_exc())
    
    # If running in rebuild mode (-r)
    if args.rebuild:
        rebuild()
    # If NOT keeping Solr index (-k)
    if not args.keep:
        solr_index = make_local_path(case.output_dir, case.image_name, "AutopsyTestCase", "KeywordSearch")
        if clear_dir(solr_index):
            print_report([], "DELETE SOLR INDEX", "Solr index deleted.")
    elif args.keep:
        print_report([], "KEEP SOLR INDEX", "Solr index has been kept.")
    # If running in verbose mode (-v)
    if args.verbose:
        errors = report_all_errors()
        okay = "No warnings or errors in any log files."
        print_report(errors, "VERBOSE", okay)
    # If running in exception mode (-e)
    if args.exception:
        exceptions = search_logs(args.exception_string)
        okay = "No warnings or exceptions found containing text '" + args.exception_string + "'."
        print_report(exceptions, "EXCEPTION", okay)
        
    # Now test in comparison to the gold standards
    compare_to_gold_db()
    compare_to_gold_html()
    
    # Make the CSV log and the html log viewer
    generate_csv(case.csv)
    if case.global_csv:
        generate_csv(case.global_csv)
    generate_html()
    
    # Reset the case and return the tests sucessfully finished
    case.reset()
    return True

# Tests Autopsy with RegressionTest.java by by running
# the build.xml file through ant
def run_ant():
    # Set up the directories
    test_case_path = os.path.join(case.output_dir, case.image_name)
    if dir_exists(test_case_path):
        shutil.rmtree(test_case_path)
    os.makedirs(test_case_path)
    if not dir_exists(make_local_path("gold")):
        os.makedirs(make_local_path("gold"))
    
    case.ant = ["ant"]
    case.ant.append("-q")
    case.ant.append("-f")
    case.ant.append(os.path.join("..","build.xml"))
    case.ant.append("regression-test")
    case.ant.append("-l")
    case.ant.append(case.antlog_dir)
    case.ant.append("-Dimg_path=" + case.image_file)
    case.ant.append("-Dknown_bad_path=" + case.known_bad_path)
    case.ant.append("-Dkeyword_path=" + case.keyword_path)
    case.ant.append("-Dnsrl_path=" + case.nsrl_path)
    case.ant.append("-Dgold_path=" + make_local_path(case.gold))
    case.ant.append("-Dout_path=" + make_local_path(case.output_dir, case.image_name))
    case.ant.append("-Dignore_unalloc=" + "%s" % args.unallocated)
    case.ant.append("-Dtest.timeout=" + str(case.timeout))
    
    printout("Ingesting Image:\n" + case.image_file + "\n")
    printout("CMD: " + " ".join(case.ant))
    printout("Starting test...\n")
    if SYS is OS.CYGWIN:
        subprocess.call(case.ant)
    elif SYS is OS.WIN:
        theproc = subprocess.Popen(case.ant, shell = True)
        theproc.communicate()
    
# Returns the type of image file, based off extension
class IMGTYPE:
  RAW, ENCASE, SPLIT, UNKNOWN = range(4)
def image_type(image_file):
  ext_start = image_file.rfind(".")
  if (ext_start == -1):
    return IMGTYPE.UNKNOWN
  ext = image_file[ext_start:].lower()
  if (ext == ".img" or ext == ".dd"):
    return IMGTYPE.RAW
  elif (ext == ".e01"):
    return IMGTYPE.ENCASE
  elif (ext == ".aa" or ext == ".001"):
    return IMGTYPE.SPLIT
  else:
    return IMGTYPE.UNKNOWN



#-----------------------------------------------------------#
#      Functions relating to rebuilding and comparison      #
#                   of gold standards                       #
#-----------------------------------------------------------#

# Rebuilds the gold standards by copying the test-generated database
# and html report files into the gold directory
def rebuild():
    # Errors to print
    errors = []
    # Delete the current gold standards
    gold_dir = make_local_path(case.gold, case.image_name)
    clear_dir(gold_dir)
    
    # Rebuild the database
    gold_from = make_local_path(case.output_dir, case.image_name,
                                "AutopsyTestCase", "autopsy.db")
    gold_to = make_local_path(case.gold, case.image_name, "standard.db")
    try:
        copy_file(gold_from, gold_to)
    except FileNotFoundException as e:
        errors.append(e.error)
    except Exception as e:
        errors.append("Error: Unknown fatal error when rebuilding the gold database.")
        errors.append(str(e) + "\n")
    
    # Rebuild the HTML report
    html_path = make_local_path(case.output_dir, case.image_name,
                                  "AutopsyTestCase", "Reports")
    try:     
        html_from = get_file_in_dir(html_path, ".html")
        html_to = make_local_path(case.gold, case.image_name, "standard.html")
        copy_file(html_from, html_to)
    except FileNotFoundException as e:
        errors.append(e.error)
    except Exception as e:
        errors.append("Error: Unknown fatal error when rebuilding the gold html report.")
        errors.append(str(e) + "\n")
    
    okay = "Sucessfully rebuilt all gold standards."
    print_report(errors, "REBUILDING", okay)

# Using the global case's variables, compare the database file made by the
# regression test to the gold standard database file
# Initializes the global database, which stores the information retrieved
# from queries while comparing
def compare_to_gold_db():
    # SQLITE needs unix style pathing
    gold_db_file = os.path.join("./", case.gold, case.image_name, "standard.db")
    autopsy_db_file = os.path.join("./", case.output_dir, case.image_name,
                                      "AutopsyTestCase", "autopsy.db")
    # Try to query the databases. Ignore any exceptions, the function will
    # return an error later on if these do fail
    database.clear()
    try:
        database.generate_gold_objects()
        database.generate_gold_artifacts()
        database.generate_gold_attributes()
    except:
        pass
    try:
        database.generate_autopsy_objects()
        database.generate_autopsy_artifacts()
        database.generate_autopsy_attributes()
    except:
        pass
    # This is where we return if a file doesn't exist, because we don't want to
    # compare faulty databases, but we do however want to try to run all queries
    # regardless of the other database
    if not file_exists(autopsy_db_file):
        printerror("Error: Database file does not exist at:")
        printerror(autopsy_db_file + "\n")
        return
    if not file_exists(gold_db_file):
        printerror("Error: Gold database file does not exist at:")
        printerror(gold_db_file + "\n")
        return
        
    # compare size of bb artifacts, attributes, and tsk objects
    gold_con = sqlite3.connect(gold_db_file)
    gold_cur = gold_con.cursor()
    autopsy_con = sqlite3.connect(autopsy_db_file)
    autopsy_cur = autopsy_con.cursor()
    
    exceptions = []
    # Testing tsk_objects
    exceptions.append(compare_tsk_objects())
    # Testing blackboard_artifacts
    exceptions.append(compare_bb_artifacts())
    # Testing blackboard_attributes
    exceptions.append(compare_bb_attributes())
    
    database.artifact_comparison = exceptions[1]
    database.attribute_comparison = exceptions[2]
    
    okay = "All counts match."
    print_report(exceptions[0], "COMPARE TSK OBJECTS", okay)
    print_report(exceptions[1], "COMPARE ARTIFACTS", okay)
    print_report(exceptions[2], "COMPARE ATTRIBUTES", okay)
    
# Using the global case's variables, compare the html report file made by
# the regression test against the gold standard html report
def compare_to_gold_html():
    gold_html_file = make_local_path(case.gold, case.image_name, "standard.html")
    autopsy_html_path = make_local_path(case.output_dir, case.image_name,
                                        "AutopsyTestCase", "Reports")
    try:
        autopsy_html_file = get_file_in_dir(autopsy_html_path, ".html")
                
        if not file_exists(gold_html_file):
            printerror("Error: No gold html report exists at:")
            printerror(gold_html_file + "\n")
            return
        if not file_exists(autopsy_html_file):
            printerror("Error: No case html report exists at:")
            printerror(autopsy_html_file + "\n")
            return
        
        errors = []
        errors = compare_report_files(autopsy_html_file, gold_html_file)
        okay = "The test report matches the gold report."
        print_report(errors, "REPORT COMPARISON", okay)
        if not errors:
            case.report_passed = True
    except FileNotFoundException as e:
        e.print_error()
    except DirNotFoundException as e:
        e.print_error()
    except Exception as e:
        printerror("Error: Unknown fatal error comparing reports.")
        printerror(str(e) + "\n")
        logging.critical(traceback.format_exc())

# Compares the blackboard artifact counts of two databases
# given the two database cursors
def compare_bb_artifacts():
    exceptions = []
    try:
        for type_id in range(1, 13):
            if database.gold_artifacts != database.autopsy_artifacts:
                error = str("Artifact counts do not match for type id %d. " % type_id)
                error += str("Gold: %d, Test: %d" %
                            (database.gold_artifacts[type_id],
                             database.autopsy_artifacts[type_id]))
                exceptions.append(error)
                return exceptions
    except Exception as e:
        exceptions.append("Error: Unable to compare blackboard_artifacts.\n")
        return exceptions

# Compares the blackboard atribute counts of two databases
# given the two database cursors
def compare_bb_attributes():
    exceptions = []
    try:
        if database.gold_attributes != database.autopsy_attributes:
            error = "Attribute counts do not match. "
            error += str("Gold: %d, Test: %d" % (database.gold_attributes, database.autopsy_attributes))
            exceptions.append(error)
            return exceptions
    except Exception as e:
        exceptions.append("Error: Unable to compare blackboard_attributes.\n")
        return exceptions

# Compares the tsk object counts of two databases
# given the two database cursors
def compare_tsk_objects():
    exceptions = []
    try:
        if database.gold_objects != database.autopsy_objects:
            error = "TSK Object counts do not match. "
            error += str("Gold: %d, Test: %d" % (database.gold_objects, database.autopsy_objects))
            exceptions.append(error)
            return exceptions
    except Exception as e:
        exceptions.append("Error: Unable to compare tsk_objects.\n")
        return exceptions



#-------------------------------------------------#
#      Functions relating to error reporting      #
#-------------------------------------------------#      

# Generate the "common log": a log of all exceptions and warnings
# from each log file generated by Autopsy
def generate_common_log():
    try:
        logs_path = make_local_path(case.output_dir, case.image_name, "logs")
        common_log = codecs.open(case.common_log, "a", "latin-1")
        common_log.write("--------------------------------------------------\n")
        common_log.write(case.image_name + "\n")
        common_log.write("--------------------------------------------------\n")
        for file in os.listdir(logs_path):
            log = codecs.open(make_path(logs_path, file), "r", "latin-1")
            for line in log:
                if "exception" in line.lower():
                    common_log.write("From " + file +":\n" +  line + "\n")
                if "warning" in line.lower():
                    common_log.write("From " + file +":\n" +  line + "\n")
                if "error" in line.lower():
                    common_log.write("From " + file +":\n" +  line + "\n")
            log.close()
        common_log.write("\n\n")
        common_log.close()
    except Exception as e:
        printerror("Error: Unable to generate the common log.")
        printerror(str(e))
        logging.critical(traceback.format_exc())

# Fill in the global case's variables that require the log files
def fill_case_data():
    try:
        # Open autopsy.log.0
        log_path = make_local_path(case.output_dir, case.image_name, "logs", "autopsy.log.0")
        log = open(log_path)
        
        # Set the case starting time based off the first line of autopsy.log.0
        # *** If logging time format ever changes this will break ***
        case.start_date = log.readline().split(" org.")[0]
    
        # Set the case ending time based off the "create" time (when the file was copied)
        case.end_date = time.ctime(os.path.getmtime(log_path))
    except Exception as e:
        printerror("Error: Unable to open autopsy.log.0.")
        printerror(str(e) + "\n")
        logging.warning(traceback.format_exc())
    
    # Set the case total test time
    # Start date must look like: "Jul 16, 2012 12:57:53 PM"
    # End date must look like: "Mon Jul 16 13:02:42 2012"
    # *** If logging time format ever changes this will break ***
    start = datetime.datetime.strptime(case.start_date, "%b %d, %Y %I:%M:%S %p")
    end = datetime.datetime.strptime(case.end_date, "%a %b %d %H:%M:%S %Y")
    case.total_test_time = str(end - start)
    
    try:
        # Set Autopsy version, heap space, ingest time, and service times
        version_line = search_logs("INFO: Application name: Autopsy, version:")[0]
        case.autopsy_version = get_word_at(version_line, 5).rstrip(",")
        
        case.heap_space = search_logs("Heap memory usage:")[0].rstrip().split(": ")[1]
        
        ingest_line = search_logs("Ingest (including enqueue)")[0]
        case.total_ingest_time = get_word_at(ingest_line, 5).rstrip()
        
        message_line = search_log_set("autopsy", "Ingest messages count:")[0]
        case.ingest_messages = int(message_line.rstrip().split(": ")[2])
        
        files_line = search_log_set("autopsy", "Indexed files count:")[0]
        case.indexed_files = int(files_line.rstrip().split(": ")[2])
        
        chunks_line = search_log_set("autopsy", "Indexed file chunks count:")[0]
        case.indexed_chunks = int(chunks_line.rstrip().split(": ")[2])
    except Exception as e:
        printerror("Error: Unable to find the required information to fill case data.")
        printerror(str(e) + "\n")
        logging.critical(traceback.format_exc())
    try:
        service_lines = search_log("autopsy.log.0", "to process()")
        service_list = []
        for line in service_lines:
            words = line.split(" ")
            # Kind of forcing our way into getting this data
            # If this format changes, the tester will break
            i = words.index("secs.")
            times = words[i-4] + " "
            times += words[i-3] + " "
            times += words[i-2] + " "
            times += words[i-1] + " "
            times += words[i]
            service_list.append(times)
        case.service_times = "; ".join(service_list)
    except FileNotFoundException as e:
        e.print_error()
    except Exception as e:
        printerror("Error: Unknown fatal error when finding service times.")
        printerror(str(e) + "\n")
        logging.critical(traceback.format_exc())
    
# Generate the CSV log file
def generate_csv(csv_path):
    try:
        # If the CSV file hasn't already been generated, this is the
        # first run, and we need to add the column names
        if not file_exists(csv_path):
            csv_header(csv_path)
            
        # Now add on the fields to a new row
        csv = open(csv_path, "a")
        
        # Variables that need to be written
        vars = []
        vars.append( case.image_file )
        vars.append( case.image_name )
        vars.append( case.output_dir )
        vars.append( socket.gethostname() )
        vars.append( case.autopsy_version )
        vars.append( case.heap_space )
        vars.append( case.start_date )
        vars.append( case.end_date )
        vars.append( case.total_test_time )
        vars.append( case.total_ingest_time )
        vars.append( case.service_times )
        vars.append( str(len(get_exceptions())) )
        vars.append( str(get_num_memory_errors("autopsy")) )
        vars.append( str(get_num_memory_errors("tika")) )
        vars.append( str(get_num_memory_errors("solr")) )
        vars.append( str(len(search_log_set("autopsy", "TskCoreException"))) )
        vars.append( str(len(search_log_set("autopsy", "TskDataException"))) )
        vars.append( str(case.ingest_messages) )
        vars.append( str(case.indexed_files) )
        vars.append( str(case.indexed_chunks) )
        vars.append( str(len(search_log_set("autopsy", "Stopping ingest due to low disk space on disk"))) )
        vars.append( str(database.autopsy_objects) )
        vars.append( str(database.get_artifacts_count()) )
        vars.append( str(database.autopsy_attributes) )
        vars.append( make_local_path("gold", case.image_name, "standard.db") )
        vars.append( database.get_artifact_comparison() )
        vars.append( database.get_attribute_comparison() )
        vars.append( make_local_path("gold", case.image_name, "standard.html") )
        vars.append( str(case.report_passed) )
        vars.append( case.ant_to_string() )
        
        # Join it together with a ", "
        output = "|".join(vars)
        output += "\n"
        # Write to the log!
        csv.write(output)
        csv.close()
    except Exception as e:
        printerror("Error: Unknown fatal error when creating CSV file at:")
        printerror(csv_path)
        printerror(str(e) + "\n")
        logging.critical(traceback.format_exc())

# Generates the CSV header (column names)
def csv_header(csv_path):
    csv = open(csv_path, "w")
    titles = []
    titles.append("Image Path")
    titles.append("Image Name")
    titles.append("Output Case Directory")
    titles.append("Host Name")
    titles.append("Autopsy Version")
    titles.append("Heap Space Setting")
    titles.append("Test Start Date")
    titles.append("Test End Date")
    titles.append("Total Test Time")
    titles.append("Total Ingest Time")
    titles.append("Service Times")
    titles.append("Autopsy Exceptions")
    titles.append("Autopsy OutOfMemoryErrors/Exceptions")
    titles.append("Tika OutOfMemoryErrors/Exceptions")
    titles.append("Solr OutOfMemoryErrors/Exceptions")
    titles.append("TskCoreExceptions")
    titles.append("TskDataExceptions")
    titles.append("Ingest Messages Count")
    titles.append("Indexed Files Count")
    titles.append("Indexed File Chunks Count")
    titles.append("Out Of Disk Space")
    titles.append("Tsk Objects Count")
    titles.append("Artifacts Count")
    titles.append("Attributes Count")
    titles.append("Gold Database Name")
    titles.append("Artifacts Comparison")
    titles.append("Attributes Comparison")
    titles.append("Gold Report Name")
    titles.append("Report Comparison")
    titles.append("Ant Command Line")
    output = "|".join(titles)
    output += "\n"
    csv.write(output)
    csv.close()
        
# Returns a list of all the exceptions listed in all the autopsy logs
def get_exceptions():
    exceptions = []
    logs_path = make_local_path(case.output_dir, case.image_name, "logs")
    results = []
    for file in os.listdir(logs_path):
        if "autopsy.log" in file:
            log = codecs.open(make_path(logs_path, file), "r", "latin-1")
            ex = re.compile("\SException")
            er = re.compile("\SError")
            for line in log:
                if ex.search(line) or er.search(line):
                    exceptions.append(line)
            log.close()
    return exceptions
    
# Returns a list of all the warnings listed in the common log
def get_warnings():
    warnings = []
    common_log = codecs.open(case.common_log, "r", "latin-1")
    for line in common_log:
        if "warning" in line.lower():
            warnings.append(line)
    common_log.close()
    return warnings

# Returns all the errors found in the common log in a list
def report_all_errors():
    try:
        return get_warnings() + get_exceptions()
    except Exception as e:
        printerror("Error: Unknown fatal error when reporting all errors.")
        printerror(str(e) + "\n")
        logging.warning(traceback.format_exc())

# Searched all the known logs for the given regex
# The function expects regex = re.compile(...)
def regex_search_logs(regex):
    logs_path = make_local_path(case.output_dir, case.image_name, "logs")
    results = []
    for file in os.listdir(logs_path):
        log = codecs.open(make_path(logs_path, file), "r", "latin-1")
        for line in log:
            if regex.search(line):
                results.append(line)
        log.close()
    if results:
        return results

# Search through all the known log files for a specific string.
# Returns a list of all lines with that string
def search_logs(string):
    logs_path = make_local_path(case.output_dir, case.image_name, "logs")
    results = []
    for file in os.listdir(logs_path):
        log = codecs.open(make_path(logs_path, file), "r", "latin-1")
        for line in log:
            if string in line:
                results.append(line)
        log.close()
    return results
    
# Searches the common log for any instances of a specific string.
def search_common_log(string):
    results = []
    log = codecs.open(case.common_log, "r", "latin-1")
    for line in log:
        if string in line:
            results.append(line)
    log.close()
    return results

# Searches the given log for the given string
# Returns a list of all lines with that string
def search_log(log, string):
    logs_path = make_local_path(case.output_dir, case.image_name, "logs", log)
    try:
        results = []
        log = codecs.open(logs_path, "r", "latin-1")
        for line in log:
            if string in line:
                results.append(line)
        log.close()
        if results:
            return results
    except:
        raise FileNotFoundException(logs_path)

# Search through all the the logs of the given type
# Types include autopsy, tika, and solr
def search_log_set(type, string):
    logs_path = make_local_path(case.output_dir, case.image_name, "logs")
    results = []
    for file in os.listdir(logs_path):
        if type in file:
            log = codecs.open(make_path(logs_path, file), "r", "latin-1")
            for line in log:
                if string in line:
                    results.append(line)
            log.close()
    return results
        
# Returns the number of OutOfMemoryErrors and OutOfMemoryExceptions
# for a certain type of log
def get_num_memory_errors(type):
    return (len(search_log_set(type, "OutOfMemoryError")) + 
            len(search_log_set(type, "OutOfMemoryException")))

# Print a report for the given errors with the report name as name
# and if no errors are found, print the okay message
def print_report(errors, name, okay):
    if errors:
        printerror("--------< " + name + " >----------")
        for error in errors:
            printerror(error)
        printerror("--------< / " + name + " >--------\n")
    else:
        printout("-----------------------------------------------------------------")
        printout("< " + name + " - " + okay + " />")
        printout("-----------------------------------------------------------------\n")

# Used instead of the print command when printing out an error
def printerror(string):
    print(string)
    case.printerror.append(string)

# Used instead of the print command when printing out anything besides errors
def printout(string):
    print(string)
    case.printout.append(string)

# Generates the HTML log file
def generate_html():
    # If the file doesn't exist yet, this is the first case to run for
    # this test, so we need to make the start of the html log
    if not file_exists(case.html_log):
        write_html_head()
    try:
        html = open(case.html_log, "a")
        # The image title
        title = "<h1><a name='" + case.image_name + "'>" + case.image_name + " \
                    <span>tested on <strong>" + socket.gethostname() + "</strong></span></a></h1>\
                 <h2 align='center'>\
                 <a href='#" + case.image_name + "-errors'>Errors and Warnings</a> |\
                 <a href='#" + case.image_name + "-info'>Information</a> |\
                 <a href='#" + case.image_name + "-general'>General Output</a> |\
                 <a href='#" + case.image_name + "-logs'>Logs</a>\
                 </h2>"
                 
        # The script errors found
        errors = "<div id='errors'>\
                  <h2><a name='" + case.image_name + "-errors'>Errors and Warnings</a></h2>\
                  <hr color='#FF0000'>"
        # For each error we have logged in the case
        for error in case.printerror:
            # Replace < and > to avoid any html display errors
            errors += "<p>" + error.replace("<", "&lt").replace(">", "&gt") + "</p>"
            # If there is a \n, we probably want a <br /> in the html
            if "\n" in error:
                errors += "<br />"
        errors += "</div>"
        
        # Links to the logs
        logs = "<div id='logs'>\
                <h2><a name='" + case.image_name + "-logs'>Logs</a></h2>\
                <hr color='#00a00f'>"
        logs_path = make_local_path(case.output_dir, case.image_name, "logs")
        for file in os.listdir(logs_path):
            logs += "<p><a href='file:\\" + make_path(logs_path, file) + "' target='_blank'>" + file + "</a></p>"
        logs += "</div>"
        
        # All the testing information
        info = "<div id='info'>\
                <h2><a name='" + case.image_name + "-info'>Information</a></h2>\
                <hr color='#0005FF'>\
                <table cellspacing='5px'>"
        # The individual elements
        info += "<tr><td>Image Path:</td>"
        info += "<td>" + case.image_file + "</td></tr>"
        info += "<tr><td>Image Name:</td>"
        info += "<td>" + case.image_name + "</td></tr>"
        info += "<tr><td>Case Output Directory:</td>"
        info += "<td>" + case.output_dir + "</td></tr>"
        info += "<tr><td>Autopsy Version:</td>"
        info += "<td>" + case.autopsy_version + "</td></tr>"
        info += "<tr><td>Heap Space:</td>"
        info += "<td>" + case.heap_space + "</td></tr>"
        info += "<tr><td>Test Start Date:</td>"
        info += "<td>" + case.start_date + "</td></tr>"
        info += "<tr><td>Test End Date:</td>"
        info += "<td>" + case.end_date + "</td></tr>"
        info += "<tr><td>Total Test Time:</td>"
        info += "<td>" + case.total_test_time + "</td></tr>"
        info += "<tr><td>Total Ingest Time:</td>"
        info += "<td>" + case.total_ingest_time + "</td></tr>"
        info += "<tr><td>Exceptions Count:</td>"
        info += "<td>" + str(len(get_exceptions())) + "</td></tr>"
        info += "<tr><td>Autopsy OutOfMemoryExceptions:</td>"
        info += "<td>" + str(len(search_logs("OutOfMemoryException"))) + "</td></tr>"
        info += "<tr><td>Autopsy OutOfMemoryErrors:</td>"
        info += "<td>" + str(len(search_logs("OutOfMemoryError"))) + "</td></tr>"
        info += "<tr><td>Tika OutOfMemoryErrors/Exceptions:</td>"
        info += "<td>" + str(get_num_memory_errors("tika")) + "</td></tr>"
        info += "<tr><td>Solr OutOfMemoryErrors/Exceptions:</td>"
        info += "<td>" + str(get_num_memory_errors("solr")) + "</td></tr>"
        info += "<tr><td>TskCoreExceptions:</td>"
        info += "<td>" + str(len(search_log_set("autopsy", "TskCoreException"))) + "</td></tr>"
        info += "<tr><td>TskDataExceptions:</td>"
        info += "<td>" + str(len(search_log_set("autopsy", "TskDataException"))) + "</td></tr>"
        info += "<tr><td>Ingest Messages Count:</td>"
        info += "<td>" + str(case.ingest_messages) + "</td></tr>"
        info += "<tr><td>Indexed Files Count:</td>"
        info += "<td>" + str(case.indexed_files) + "</td></tr>"
        info += "<tr><td>Indexed File Chunks Count:</td>"
        info += "<td>" + str(case.indexed_chunks) + "</td></tr>"
        info += "<tr><td>Out Of Disk Space:\
                         <p style='font-size: 11px;'>(will skew other test results)</p></td>"
        info += "<td>" + str(len(search_log_set("autopsy", "Stopping ingest due to low disk space on disk"))) + "</td></tr>"
        info += "<tr><td>TSK Objects Count:</td>"
        info += "<td>" + str(database.autopsy_objects) + "</td></tr>"
        info += "<tr><td>Artifacts Count:</td>"
        info += "<td>" + str(database.get_artifacts_count()) + "</td></tr>"
        info += "<tr><td>Attributes Count:</td>"
        info += "<td>" + str(database.autopsy_attributes) + "</td></tr>"
        info += "</table>\
                 </div>"
        # For all the general print statements in the case
        output = "<div id='general'>\
                  <h2><a name='" + case.image_name + "-general'>General Output</a></h2>\
                  <hr color='#282828'>"
        # For each printout in the case's list
        for out in case.printout:
            output += "<p>" + out + "</p>"
            # If there was a \n it probably means we want a <br /> in the html
            if "\n" in out:
                output += "<br />"
        output += "</div>"
        
        html.write(title)
        html.write(errors)
        html.write(info)
        html.write(logs)
        html.write(output)
        html.close()
    except Exception as e:
        printerror("Error: Unknown fatal error when creating HTML log at:")
        printerror(case.html_log)
        printerror(str(e) + "\n")    
        logging.critical(traceback.format_exc())

# Writed the top of the HTML log file
def write_html_head():
    html = open(case.html_log, "a")
    head = "<html>\
            <head>\
            <title>AutopsyTestCase Output</title>\
            </head>\
            <style type='text/css'>\
            body { font-family: 'Courier New'; font-size: 12px; }\
            h1 { background: #444; margin: 0px auto; padding: 0px; color: #FFF; border: 1px solid #000; font-family: Tahoma; text-align: center; }\
            h1 span { font-size: 12px; font-weight: 100; }\
            h2 { font-family: Tahoma; padding: 0px; margin: 0px; }\
            hr { width: 100%; height: 1px; border: none; margin-top: 10px; margin-bottom: 10px; }\
            #errors { background: #FFCFCF; border: 1px solid #FF0000; color: #FF0000; padding: 10px; margin: 20px; }\
            #info { background: #D2D3FF; border: 1px solid #0005FF; color: #0005FF; padding: 10px; margin: 20px; }\
            #general { background: #CCCCCC; border: 1px solid #282828; color: #282828; padding: 10px; margin: 20px; }\
            #logs { background: #8cff97; border: 1px solid #00820c; color: #00820c; padding: 10px; margin: 20px; }\
            #errors p, #info p, #general p, #logs p { pading: 0px; margin: 0px; margin-left: 5px; }\
            #info table td { color: #0005FF; font-size: 12px; min-width: 225px; }\
            #logs a { color: #00820c; }\
            </style>\
            <body>"
    html.write(head)
    html.close()

# Writed the bottom of the HTML log file
def write_html_foot():
    html = open(case.html_log, "a")
    head = "</body></html>"
    html.write(head)
    html.close()

# Adds all the image names to the HTML log for easy access
def html_add_images(full_image_names):
    # If the file doesn't exist yet, this is the first case to run for
    # this test, so we need to make the start of the html log
    if not file_exists(case.html_log):
        write_html_head()
    html = open(case.html_log, "a")
    links = []
    for full_name in full_image_names:
        name = case.get_image_name(full_name)
        links.append("<a href='#" + name + "'>" + name + "</a>")
    html.write("<p align='center'>" + (" | ".join(links)) + "</p>")



#----------------------------------#
#         Helper functions         #
#----------------------------------#

# Verifies a file's existance
def file_exists(file):
    try:
        if os.path.exists(file):
            return os.path.isfile(file)
    except:
        return False
        
# Verifies a directory's existance
def dir_exists(dir):
    try:
        return os.path.exists(dir)
    except:
        return False

# Returns a Windows style path starting with the cwd and
# ending with the list of directories given
def make_local_path(*dirs):
    path = wgetcwd()
    for dir in dirs:
        path += ("\\" + dir)
    return path_fix(path)

# Returns a Windows style path based only off the given directories
def make_path(*dirs):
    path = dirs[0]
    for dir in dirs[1:]:
        path += ("\\" + dir)
    return path_fix(path)
    
# Fix a standard os.path by making it Windows format
def path_fix(path):
    return path.replace("/", "\\")

# Gets the true current working directory instead of Cygwin's
def wgetcwd():
    if SYS is OS.CYGWIN:
        proc = subprocess.Popen(("cygpath", "-m", os.getcwd()), stdout=subprocess.PIPE)
        out,err = proc.communicate()
        return out.rstrip()
    elif SYS is OS.WIN:
        return os.getcwd()

# Copy the log files from Autopsy's default directory
def copy_logs():
    try:
        log_dir = os.path.join("..","build","test","qa-functional","work","userdir0","var","log")
        shutil.copytree(log_dir, make_local_path(case.output_dir, case.image_name, "logs"))
    except Exception as e:
        printerror("Error: Failed to copy the logs.")
        printerror(str(e) + "\n")
        logging.warning(traceback.format_exc())

# Clears all the files from a directory and remakes it
def clear_dir(dir):
    try:
        if dir_exists(dir):
            shutil.rmtree(dir)
        os.makedirs(dir)
        return True;
    except:
        printerror("Error: Cannot clear the given directory:")
        printerror(dir + "\n")
        return False;

# Copies a given file from "ffrom" to "to"
def copy_file(ffrom, to):
    try :
        if not file_exists(ffrom):
            raise FileNotFoundException(ffrom)
        shutil.copy(ffrom, to)
    except:
        raise FileNotFoundException(to)

# Returns the first file in the given directory with the given extension
def get_file_in_dir(dir, ext):
    try:
        for file in os.listdir(dir):
            if file.endswith(ext):
                return make_path(dir, file)
        # If nothing has been found, raise an exception
        raise FileNotFoundException(dir)
    except:
        raise DirNotFoundException(dir)

# Compares file a to file b and any differences are returned
# Only works with report html files, as it searches for the first <ul>
def compare_report_files(a_path, b_path):
    a_file = open(a_path)
    b_file = open(b_path)
    a = a_file.read()
    b = b_file.read()
    a = a[a.find("<ul>"):]
    b = b[b.find("<ul>"):]
    
    a_list = split(a, 50)
    b_list = split(b, 50)
    exceptions = []
    if not len(a_list) == len(b_list):
        exceptions.append("The reports do not match.")
        test = "The test HTML report has " + str(len(a_list)) + " segments."
        gold = "The gold HTML report has " + str(len(b_list)) + " segments."
        exceptions.append(test)
        exceptions.append(gold)
    return exceptions

# Split a string into an array of string of the given size
def split(input, size):
    return [input[start:start+size] for start in range(0, len(input), size)]

# Returns the nth word in the given string or "" if n is out of bounds
# n starts at 0 for the first word
def get_word_at(string, n):
    words = string.split(" ")
    if len(words) >= n:
        return words[n]
    else:
        return ""

# Returns true if the given file is one of the required input files
# for ingest testing
def required_input_file(name):
    if ((name == "notablehashes.txt-md5.idx") or
       (name == "notablekeywords.xml") or
       (name == "nsrl.txt-md5.idx")): 
       return True
    else:
        return False

        

# Returns the args of the test script
def usage():
    return """
Usage:  ./regression.py [-f FILE] [OPTIONS]

        Run RegressionTest.java, and compare the result with a gold standard.
        By default, the script tests every image in ./input
        When the -f flag is set, this script only tests a single given image.
        When the -l flag is set, the script looks for a configuration file,
        which may outsource to a new input directory and to individual images.
        
        Expected files:
          An NSRL database at:            ./input/nsrl.txt-md5.idx
          A notable hash database at:     ./input/notablehashes.txt-md5.idx
          A notible keyword file at:      ./input/notablekeywords.xml
        
Options:
  -r            Rebuild the gold standards for the image(s) tested.
  -i            Ignores the ./input directory and all files within it.
  -u            Tells Autopsy not to ingest unallocated space.
  -k            Keeps each image's Solr index instead of deleting it.
  -v            Verbose mode; prints all errors to the screen.
  -e ex         Prints out all errors containing ex.
  -l cfg        Runs from configuration file cfg.
    """




#------------------------------------------------------------#
# Exception classes to manage "acceptable" thrown exceptions #
#          versus unexpected and fatal exceptions            #
#------------------------------------------------------------#

# If a file cannot be found by one of the helper functions
# they will throw a FileNotFoundException unless the purpose
# is to return False
class FileNotFoundException(Exception):
    def __init__(self, file):
        self.file = file
        self.strerror = "FileNotFoundException: " + file
        
    def print_error(self):
        printerror("Error: File could not be found at:")
        printerror(self.file + "\n")
        
    def error(self):
        error = "Error: File could not be found at:\n" + self.file + "\n"
        return error

# If a directory cannot be found by a helper function,
# it will throw this exception
class DirNotFoundException(Exception):
    def __init__(self, dir):
        self.dir = dir
        self.strerror = "DirNotFoundException: " + dir
        
    def print_error(self):
        printerror("Error: Directory could not be found at:")
        printerror(self.dir + "\n")
        
    def error(self):
        error = "Error: Directory could not be found at:\n" + self.dir + "\n"
        return error

 
        
#----------------------#
#         Main         #
#----------------------#
def main():
    # Global variables
    global args
    global case
    global database
    case = TestAutopsy()
    database = Database()

    printout("")
    args = Args()
    # The arguments were given wrong:
    if not args.parse():
        case.reset()
        pass
    # Otherwise test away!
    else:
        case.output_dir = make_path("output", time.strftime("%Y.%m.%d-%H.%M.%S"))
        os.makedirs(case.output_dir)
        case.common_log = make_local_path(case.output_dir, "AutopsyErrors.txt")
        case.csv = make_local_path(case.output_dir, "CSV.txt")
        case.html_log = make_local_path(case.output_dir, "AutopsyTestCase.html")
        log_name = case.output_dir + "\\regression.log"
        logging.basicConfig(filename=log_name, level=logging.DEBUG)
        
        # If user wants to do a single file and a list (contradictory?)
        if args.single and args.list:
            printerror("Error: Cannot run both from config file and on a single file.")
            return
        # If working from a configuration file
        if args.list:
            if not file_exists(args.config_file):
                printerror("Error: Configuration file does not exist at:")
                printerror(args.config_file)
                return
            run_config_test(args.config_file)
        # Else if working on a single file
        elif args.single:
            if not file_exists(args.single_file):
                printerror("Error: Image file does not exist at:")
                printerror(args.single_file)
                return
            run_test(args.single_file)
        # If user has not selected a single file, and does not want to ignore
        #  the input directory, continue on to parsing ./input
        if (not args.single) and (not args.ignore):
            for file in os.listdir(case.input_dir):
                # Make sure it's not a required hash/keyword file or dir
                if (not required_input_file(file) and
                    not os.path.isdir(make_path(case.input_dir, file))):
                    run_test(make_path(case.input_dir, file))
               
        write_html_foot()

class OS:
  LINUX, MAC, WIN, CYGWIN = range(4)      
if __name__ == "__main__":
    global SYS
    if _platform == "linux" or _platform == "linux2":
        SYS = OS.LINUX
    elif _platform == "darwin":
        SYS = OS.MAC
    elif _platform == "win32":
        SYS = OS.WIN
    elif _platform == "cygwin":
        SYS = OS.CYGWIN
        
    if SYS is OS.WIN or SYS is OS.CYGWIN:
        main()
    else:
        print("We only support Windows and Cygwin at this time.")