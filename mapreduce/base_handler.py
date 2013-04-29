#!/usr/bin/env python
#
# Copyright 2010 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Base handler class for all mapreduce handlers."""



# pylint: disable=g-bad-name

import httplib
import logging
from mapreduce.lib import simplejson

try:
  from mapreduce.lib import pipeline
except ImportError:
  pipeline = None
from google.appengine.ext import webapp
from mapreduce import errors
from mapreduce import model
from mapreduce import util


class Error(Exception):
  """Base-class for exceptions in this module."""


class BadRequestPathError(Error):
  """The request path for the handler is invalid."""


class BaseHandler(webapp.RequestHandler):
  """Base class for all mapreduce handlers."""

  def base_path(self):
    """Base path for all mapreduce-related urls."""
    path = self.request.path
    return path[:path.rfind("/")]


class TaskQueueHandler(BaseHandler):
  """Base class for handlers intended to be run only from the task queue.

  Sub-classes should implement the 'handle' method.
  """

  def post(self):
    if "X-AppEngine-QueueName" not in self.request.headers:
      logging.error(self.request.headers)
      logging.error("Task queue handler received non-task queue request")
      self.response.set_status(
          403, message="Task queue handler received non-task queue request")
      return
    self._setup()
    self.handle()

  def _setup(self):
    """Called before handle method to set up handler."""
    pass

  def handle(self):
    """To be implemented by subclasses."""
    raise NotImplementedError()

  def task_retry_count(self):
    """Number of times this task has been retried."""
    return int(self.request.headers.get("X-AppEngine-TaskExecutionCount", 0))

  def retry_task(self):
    """Ask taskqueue to retry this task.

    Even though raising an exception can cause a task retry, it
    will flood logs with highly visible ERROR logs. Handlers should uses
    this method to perform controlled task retries. Only raise exceptions
    for those deserve ERROR log entries.
    """
    self.response.set_status(httplib.SERVICE_UNAVAILABLE, "Retry task")
    self.response.clear()


class JsonHandler(BaseHandler):
  """Base class for JSON handlers for user interface.

  Sub-classes should implement the 'handle' method. They should put their
  response data in the 'self.json_response' dictionary. Any exceptions raised
  by the sub-class implementation will be sent in a JSON response with the
  name of the error_class and the error_message.
  """

  def __init__(self, *args):
    """Initializer."""
    super(BaseHandler, self).__init__(*args)
    self.json_response = {}

  def base_path(self):
    """Base path for all mapreduce-related urls.

    JSON handlers are mapped to /base_path/command/command_name thus they
    require special treatment.
    """
    path = self.request.path
    base_path = path[:path.rfind("/")]
    if not base_path.endswith("/command"):
      raise BadRequestPathError(
          "Json handlers should have /command path prefix")
    return base_path[:base_path.rfind("/")]

  def _handle_wrapper(self):
    if self.request.headers.get("X-Requested-With") != "XMLHttpRequest":
      logging.error("Got JSON request with no X-Requested-With header")
      self.response.set_status(
          403, message="Got JSON request with no X-Requested-With header")
      return

    self.json_response.clear()
    try:
      self.handle()
    except errors.MissingYamlError:
      logging.debug("Could not find 'mapreduce.yaml' file.")
      self.json_response.clear()
      self.json_response["error_class"] = "Notice"
      self.json_response["error_message"] = "Could not find 'mapreduce.yaml'"
    except Exception, e:
      logging.exception("Error in JsonHandler, returning exception.")
      # TODO(user): Include full traceback here for the end-user.
      self.json_response.clear()
      self.json_response["error_class"] = e.__class__.__name__
      self.json_response["error_message"] = str(e)

    self.response.headers["Content-Type"] = "text/javascript"
    try:
      output = simplejson.dumps(self.json_response, cls=model.JsonEncoder)
    except:
      logging.exception("Could not serialize to JSON")
      self.response.set_status(500, message="Could not serialize to JSON")
      return
    else:
      self.response.out.write(output)

  def handle(self):
    """To be implemented by sub-classes."""
    raise NotImplementedError()


class PostJsonHandler(JsonHandler):
  """JSON handler that accepts POST requests."""

  def post(self):
    self._handle_wrapper()


class GetJsonHandler(JsonHandler):
  """JSON handler that accepts GET posts."""

  def get(self):
    self._handle_wrapper()


class HugeTaskHandler(TaskQueueHandler):
  """Base handler for processing HugeTasks."""

  class _RequestWrapper(object):
    def __init__(self, request):
      self._request = request

      self.path = self._request.path
      self.headers = self._request.headers

      self._encoded = True  # we have encoded payload.

      if (not self._request.get(util.HugeTask.PAYLOAD_PARAM) and
          not self._request.get(util.HugeTask.PAYLOAD_KEY_PARAM)):
        self._encoded = False
        return
      self._params = util.HugeTask.decode_payload(
          {util.HugeTask.PAYLOAD_PARAM:
           self._request.get(util.HugeTask.PAYLOAD_PARAM),
           util.HugeTask.PAYLOAD_KEY_PARAM:
           self._request.get(util.HugeTask.PAYLOAD_KEY_PARAM)})

    def get(self, name, default=""):
      if self._encoded:
        return self._params.get(name, default)
      else:
        return self._request.get(name, default)

    def set(self, name, value):
      if self._encoded:
        self._params.set(name, value)
      else:
        self._request.set(name, value)

  def __init__(self, *args, **kwargs):
    super(HugeTaskHandler, self).__init__(*args, **kwargs)

  def _setup(self):
    super(HugeTaskHandler, self)._setup()
    self.request = self._RequestWrapper(self.request)


# This path will be changed by build process when this is a part of SDK.
_DEFAULT_BASE_PATH = "/mapreduce"
_DEFAULT_PIPELINE_BASE_PATH = _DEFAULT_BASE_PATH + "/pipeline"


if pipeline:
  class PipelineBase(pipeline.Pipeline):
    """Base class for all pipelines within mapreduce framework.

    Rewrites base path to use pipeline library bundled with mapreduce.
    """

    def start(self, **kwargs):
      if "base_path" not in kwargs:
        kwargs["base_path"] = _DEFAULT_PIPELINE_BASE_PATH
      return pipeline.Pipeline.start(self, **kwargs)
else:
  PipelineBase = None
