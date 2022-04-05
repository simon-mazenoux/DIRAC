"""  StatesAccountingAgent sends periodically numbers of jobs and pilots in various states for various
     sites to the Monitoring system to create historical plots.

.. literalinclude:: ../ConfigTemplate.cfg
  :start-after: ##BEGIN StatesAccountingAgent
  :end-before: ##END
  :dedent: 2
  :caption: StatesAccountingAgent options
"""
from DIRAC import S_OK, S_ERROR
from DIRAC.ConfigurationSystem.Client.Helpers.Operations import Operations
from DIRAC.Core.Base.AgentModule import AgentModule
from DIRAC.Core.Utilities import Time
from DIRAC.AccountingSystem.Client.Types.WMSHistory import WMSHistory
from DIRAC.AccountingSystem.Client.DataStoreClient import DataStoreClient
from DIRAC.MonitoringSystem.Client.MonitoringReporter import MonitoringReporter
from DIRAC.WorkloadManagementSystem.DB.JobDB import JobDB
from DIRAC.WorkloadManagementSystem.DB.PilotAgentsDB import PilotAgentsDB


class StatesAccountingAgent(AgentModule):
    """Agent that every 15 minutes will report
    to the AccountingDB (MySQL) or the Monitoring DB (ElasticSearch), or both,
    a snapshot of the JobDB.
    Also sends a snapshot of PilotAgentsDB to Monitoring.
    """

    # WMSHistory fields
    __summaryKeyFieldsMapping = [
        "Status",
        "Site",
        "User",
        "UserGroup",
        "JobGroup",
        "JobType",
        "ApplicationStatus",
        "MinorStatus",
    ]
    __summaryDefinedFields = [("ApplicationStatus", "unset"), ("MinorStatus", "unset")]
    __summaryValueFieldsMapping = ["Jobs", "Reschedules"]
    __renameFieldsMapping = {"JobType": "JobSplitType"}

    # PilotsHistory fields
    __pilotKeyFields = ["TaskQueueID", "GridSite", "GridType", "Status"]
    __pilotValueFields = ["Pilots"]

    def initialize(self):
        """Standard initialization"""
        # This agent will always loop every 15 minutes
        self.am_setOption("PollingTime", 900)

        self.backends = self.am_getOption("Backends", "Accounting").replace(" ", "").split(",")
        self.monitoringEnabled = Operations().getValue("monitoringEnabled", "False")

        messageQueue = self.am_getOption("MessageQueue", "dirac.wmshistory")

        self.datastores = {}  # For storing the clients to Accounting and Monitoring

        if "Accounting" in self.backends:
            self.datastores["Accounting"] = DataStoreClient(retryGraceTime=900)
        if "Monitoring" in self.backends or self.monitoringEnabled:
            self.datastores["Monitoring"] = MonitoringReporter(
                monitoringType="WMSHistory", failoverQueueName=messageQueue
            )
            self.pilotReporter = MonitoringReporter(monitoringType="PilotsHistory")

        self.__jobDBFields = []
        for field in self.__summaryKeyFieldsMapping:
            if field == "User":
                field = "Owner"
            elif field == "UserGroup":
                field = "OwnerGroup"
            self.__jobDBFields.append(field)
        return S_OK()

    def execute(self):
        """Main execution method"""

        # PilotsHistory to Monitoring
        if self.monitoringEnabled:
            result = PilotAgentsDB.getSummarySnapshot(self.__pilotKeyFields)
            now = Time.dateTime()
            if not result["OK"]:
                self.log.error(
                    "Can't get the PilotAgentsDB summary", "%s: won't commit at this cycle" % result["Message"]
                )
                return S_ERROR()

            values = result["Value"][1]
            for record in values:
                record = record[1:]
                rD = {}
                for iP in range(len(self.__pilotKeyFields)):
                    rD[self.__pilotKeyFields[iP]] = record[iP]
                record = record[len(self.__pilotKeyFields) :]
                for iP in range(len(self.__pilotValueFields)):
                    rD[self.__pilotValueFields[iP]] = int(record[iP])
                rD["timestamp"] = int(Time.toEpoch(now))
                self.log.verbose("Adding following PilotsHistory record to Reporter: \n", rD)
                self.pilotReporter.addRecord(rD)

            self.log.info("Committing PilotsHistory to Monitoring")
            result = self.pilotReporter.commit()
            if not result["OK"]:
                self.log.error("Could not commit PilotsHistory to Monitoring")
                return S_ERROR()
            self.log.verbose("Done committing PilotsHistory to Monitoring")

        # WMSHistory to Monitoring or Accounting
        self.log.info("Committing WMSHistory to %s backend" % "and ".join(self.backends))
        result = JobDB().getSummarySnapshot(self.__jobDBFields)
        now = Time.dateTime()
        if not result["OK"]:
            self.log.error(
                "Can't get the JobDB summary", "%s: won't commit WMSHistory at this cycle" % result["Message"]
            )
            return S_ERROR()

        values = result["Value"][1]

        self.log.info("Start sending WMSHistory records")
        for record in values:
            record = record[1:]
            rD = {}
            for fV in self.__summaryDefinedFields:
                rD[fV[0]] = fV[1]
            for iP in range(len(self.__summaryKeyFieldsMapping)):
                fieldName = self.__summaryKeyFieldsMapping[iP]
                rD[self.__renameFieldsMapping.get(fieldName, fieldName)] = record[iP]
            record = record[len(self.__summaryKeyFieldsMapping) :]
            for iP in range(len(self.__summaryValueFieldsMapping)):
                rD[self.__summaryValueFieldsMapping[iP]] = int(record[iP])

            for backend in self.datastores:
                if backend.lower() == "monitoring":
                    rD["timestamp"] = int(Time.toEpoch(now))
                    self.datastores["Monitoring"].addRecord(rD)

                elif backend.lower() == "accounting":
                    acWMS = WMSHistory()
                    acWMS.setStartTime(now)
                    acWMS.setEndTime(now)
                    acWMS.setValuesFromDict(rD)
                    retVal = acWMS.checkValues()
                    if not retVal["OK"]:
                        self.log.error("Invalid WMSHistory accounting record ", "%s -> %s" % (retVal["Message"], rD))
                    else:
                        self.datastores["Accounting"].addRegister(acWMS)

        for backend, datastore in self.datastores.items():
            self.log.info("Committing WMSHistory records to %s backend" % backend)
            result = datastore.commit()
            if not result["OK"]:
                self.log.error("Couldn't commit WMSHistory to %s" % backend, result["Message"])
                return S_ERROR()
            self.log.verbose("Done committing WMSHistory to %s backend" % backend)

        return S_OK()
