"""
  This module contains methods for the validation of production definitions
"""

__RCSID__ = "$Id $"

from DIRAC import gLogger, S_OK, S_ERROR
from DIRAC.TransformationSystem.Client.TransformationClient import TransformationClient
from DIRAC.Resources.Catalog.FileCatalog import FileCatalog


class ProdValidator(object):

  def __init__(self):
    self.transClient = TransformationClient()

  def checkTransStatus(self, transID):
    res = self.transClient.getTransformationParameters(transID, 'Status')
    if not res['OK']:
      return res
    status = res['Value']
    if status != 'New':
      return S_ERROR("checkTransStatus failed : Invalid transformation status: %s" % status)

    return S_OK()

  def checkTransDependency(self, transID, parentTransID):
    """ check if the transformation and the parent transformation are linked """
    res = self.transClient.getTransformationMetaQuery(transID, 'Input')
    if not res['OK']:
      return res
    inputquery = res['Value']
    if not inputquery:
      return S_ERROR("No InputMetaQuery defined for transformation %s" % transID)

    res = self.transClient.getTransformationMetaQuery(parentTransID, 'Output')
    if not res['OK']:
      return res
    parentoutputquery = res['Value']
    if not parentoutputquery:
      return S_ERROR("No OutputMetaQuery defined for parent transformation %s" % parentTransID)

    # Check the matching between inputquery and parent outputmeta query
    # Currently very simplistic: just support expression with "=" and "in" operators
    gLogger.notice("Applying checkMatchQuery")
    res = self.checkMatchQuery(inputquery, parentoutputquery)

    if not res['OK']:
      gLogger.error("checkMatchQuery failed")
      return res
    if not res['Value']:
      return S_ERROR("checkMatchQuery result is False")

    return S_OK()

  def checkMatchQuery(self, mq, mqParent):
    """  Check the logical intersection between the two metaqueries
    """
    # Get the metadata types defined in the catalog
    catalog = FileCatalog()
    res = catalog.getMetadataFields()
    if not res['OK']:
      gLogger.error("Error in getMetadataFields: %s" % res['Message'])
      return res
    if not res['Value']:
      gLogger.error("Error: no metadata fields defined")
      return res

    MetaTypeDict = res['Value']['FileMetaFields']
    MetaTypeDict.update(res['Value']['DirectoryMetaFields'])

    res = self.checkformatQuery(mq)
    if not res['OK']:
      return res
    MetaQueryDict = res['Value']

    res = self.checkformatQuery(mqParent)
    if not res['OK']:
      return res
    ParentMetaQueryDict = res['Value']

    for meta, value in MetaQueryDict.items():
      if meta not in MetaTypeDict:
        msg = 'Metadata %s is not defined in the Catalog' % meta
        return S_ERROR(msg)
      mtype = MetaTypeDict[meta]
      if mtype not in ['VARCHAR(128)', 'int', 'float']:
        msg = 'Metatype %s is not supported' % mtype
        return S_ERROR(msg)
      if meta not in ParentMetaQueryDict:
        msg = 'Metadata %s is not in parent transformation query' % meta
        return S_ERROR(msg)
      if self.compareValues(value, ParentMetaQueryDict[meta]):
        continue
      else:
        msg = "Metadata values %s do not match with %s" % (value, ParentMetaQueryDict[meta])
        gLogger.error(msg)
        return S_OK(False)

    return S_OK(True)

  def checkformatQuery(self, MetaQueryDict):
    '''Check format query and transform all dict values in dict for uniform treatment'''
    for meta, value in MetaQueryDict.items():
      values = []
      if isinstance(value, dict):
        operation = value.keys()[0]
        if operation not in ['=', 'in']:
          msg = 'Operation %s is not supported' % operation
          return S_ERROR(msg)
      else:
        values.append(value)
        MetaQueryDict[meta] = {"in": values}

    return S_OK(MetaQueryDict)

  def compareValues(self, value, parentvalue):
    '''Very simple comparison. To be improved'''
    return set(
        value.values()[0]).issubset(
        set(
            parentvalue.values()[0])) or set(
        parentvalue.values()[0]).issubset(
        set(
            value.values()[0]))
