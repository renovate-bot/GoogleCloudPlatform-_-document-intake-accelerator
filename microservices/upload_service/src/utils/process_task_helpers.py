"""Helper functions to execute the pipeline"""
import requests
import traceback
from fastapi import HTTPException
from common.models import Document
from common.utils.logging_handler import Logger
from utils.autoapproval import get_values
from typing import List, Dict

def run_pipeline(payload: List[Dict], is_hitl: bool,is_reassign:bool):
  """Runs the entire pipeline
    Args:
    payload (ProcessTask): Consist of configs required to run the pipeline
    is_hitl : It is used to run the pipeline for unclassifed documents
    is_reassign : It is used to run the pipeline for reassigned document
  """
  Logger.info(f"Processing the documents: {payload}")
  try:
    extraction_score = None
    applications = []
    supporting_docs = []

    # For unclassified or reassigned documents set the doc_class
    if is_hitl or is_reassign:
      result = get_documents(payload)
      applications = result[0]
      supporting_docs = result[1]
    # for other cases like normal flow classify the documents
    elif not is_reassign:
      result = filter_documents(payload.get("configs"))
      applications = result[0]
      supporting_docs = result[1]

    # for normal flow and for hitl run the extraction of documents
    if is_hitl or applications or supporting_docs:
      # extract the application first
      if applications:
        for doc in applications:
          extraction_score=extract_documents(doc,document_type="application_form")
      # extract,validate and match supporting documents
      if supporting_docs:
        for doc in supporting_docs:
          # In case of reassign extraction is not required
          if not is_reassign:
            extraction_score=extract_documents(doc,document_type="supporting_documents")
            print("Reassigned flow")
            Logger.info("Executing pipeline for reassign scenario.")
          validate_match_approve(doc,extraction_score)
  except Exception as e:
    err = traceback.format_exc().replace("\n", " ")
    Logger.error(err)
    raise HTTPException(status_code=500, detail=e) from e

def get_classification(case_id: str, uid: str, gcs_url: str):
  """Call the classification API and get the type and class of
  the document"""
  base_url = "http://classification-service/classification_service/v1/"\
    "classification/classification_api"
  req_url = f"{base_url}?case_id={case_id}&uid={uid}" \
    f"&gcs_url={gcs_url}"
  response = requests.post(req_url)
  return response


def get_extraction_score(case_id: str, uid: str, document_class: str):
  """Call the Extraction API and get the extraction score"""
  base_url = "http://extraction-service/extraction_service/v1/extraction_api"
  req_url = f"{base_url}?case_id={case_id}&uid={uid}" \
    f"&doc_class={document_class}"
  response = requests.post(req_url)
  return response


def get_validation_score(case_id: str, uid: str, document_class: str):
  """Call the validation API and get the validation score"""
  base_url = "http://validation-service/validation_service/v1/validation/"\
    "validation_api"
  req_url = f"{base_url}?case_id={case_id}&uid={uid}" \
    f"&doc_class={document_class}"
  response = requests.post(req_url)
  return response


def get_matching_score(case_id: str, uid: str):
  """Call the matching API and get the matching score"""
  base_url = "http://matching-service/matching_service/v1/"\
    "match_document"
  req_url = f"{base_url}?case_id={case_id}&uid={uid}"
  response = requests.post(req_url)
  return response


def update_autoapproval_status(case_id: str, uid: str, a_status: str,
                 autoapproved_status: str, is_autoapproved: str):
  """Update auto approval status"""
  base_url = "http://document-status-service/document_status_service" \
    "/v1/update_autoapproved_status"
  req_url = f"{base_url}?case_id={case_id}&uid={uid}" \
    f"&status={a_status}&autoapproved_status={autoapproved_status}"\
    f"&is_autoapproved={is_autoapproved}"
  response = requests.post(req_url)
  return response

def filter_documents(configs: List[Dict]):
  """Filter the supporting documents and application form"""
  supporting_docs = []
  application_form = []
  for config in configs:
    case_id = config.get("case_id")
    uid = config.get("uid")
    gcs_url = config.get("gcs_url")
    cl_result = get_classification(case_id, uid, gcs_url)
    if cl_result.status_code == 200:
      document_type = cl_result.json().get("doc_type")
      document_class = cl_result.json().get("doc_class")
      Logger.info(
        f"Classification successful for {uid}:document_type:{document_type},\
      document_class:{document_class}.")

      if document_type == "application_form":
        config["document_class"] = document_class
        application_form.append(config)
      elif document_type == "supporting_documents":
        config["document_class"] = document_class
        supporting_docs.append(config)
    else:
      Logger.error(f"Classification FAILED for {uid}")
  print(
      f"Application form:{application_form} and"\
      f" supporting_docs:{supporting_docs}")
  Logger.info(
      f"Application form:{application_form} and "\
        f"supporting_docs:{supporting_docs}")
  return application_form, supporting_docs

def extract_documents(doc:Dict,document_type):
  """Perform extraction for application or supporting documents"""
  extraction_score = None
  case_id = doc.get("case_id")
  uid = doc.get("uid")
  document_class = doc.get("document_class")
  extract_res = get_extraction_score(case_id, uid, document_class)
  if extract_res.status_code == 200:
    Logger.info(f"Extraction successful for {document_type}")
    extraction_score = extract_res.json().get("score")
    # if document is application form then update autoapproval status
    if document_type == "application_form":
      autoapproval_status = get_values(None, extraction_score, None,
      document_class, document_type)
      Logger.info(
        f"autoapproval_status for application:{autoapproval_status}")
      update_autoapproval_status(
        case_id, uid, "success", autoapproval_status[0], "yes")
  else:
    Logger.error(f"extraction failed for {uid}")
  return extraction_score

def validate_match_approve(sup_doc:Dict,extraction_score):
  """Perform validation, matching and autoapproval for supporting documents"""
  validation_score=None
  matching_score=None
  case_id = sup_doc.get("case_id")
  uid = sup_doc.get("uid")
  document_class = sup_doc.get("document_class")
  document_type = "supporting_documents"
  validation_res = get_validation_score(case_id, uid, document_class)
  if validation_res.status_code == 200:
    print("====Validation successful==========")
    Logger.info(f"Validation successful for {uid}.")
    validation_score = validation_res.json().get("score")
    matching_res = get_matching_score(case_id, uid)
    if matching_res.status_code == 200:
      print("====Matching successful==========")
      Logger.info("Matching successful for {uid}.")
      matching_score = matching_res.json().get("score")
      update_autoapproval(document_class, document_type,case_id,uid,
validation_score, extraction_score, matching_score)
    else:
      Logger.error(f"Matching FAILED for {uid}")
  else:
    Logger.error(f"Extraction FAILED for {uid}")
  return validation_score,matching_score

def update_autoapproval(document_class, document_type,case_id,uid,
validation_score=None, extraction_score=None, matching_score=None):
  """Get the autoapproval status and update."""
  autoapproval_status = get_values(
    validation_score, extraction_score, matching_score,
    document_class, document_type)
  Logger.info(
    f"autoapproval_status for application:{autoapproval_status}")
  update_autoapproval_status(
    case_id, uid, "success", autoapproval_status[0], "yes")

def get_documents(payload:List[Dict]):
  """Filter documents for unclassified or reassigned case"""
  applications=[]
  supporting_docs=[]
  document_type = payload.get("configs")[0].get("document_type")
  if document_type == "application_form":
    apps = payload.get("configs")[0]
    applications.append(apps)
  elif document_type == "supporting_documents":
    supporting_docs.append(payload.get("configs")[0])
  print(
    f"Unclassified/Reassigned flow: Application form: {applications}\
       and supporting_docs:{supporting_docs}")
  Logger.info(
    f"Unclassified/Reassigned flow: Application form:{applications}\
       and supporting_docs:{supporting_docs}")

  return applications,supporting_docs
