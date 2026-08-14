bind = "0.0.0.0:8000"
workers = 3
timeout = 60
accesslog = "-"
errorlog = "-"

# Use the path atom instead of the request-line atom so beneficiary searches
# and report filters cannot place query-string values in access logs.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(D)s'
