import json


SCHEMA = json.loads(r"""
{
  "$schema": "http://json-schema.org/schema#",

  "definitions": {
    "byte_count": {
      "oneOf": [
        {
          "type": "string",
          "pattern": "^[0-9]+[\\.]{0,1}[0-9]*(([KMGTP])|([KMGTP]B)){0,1}$"
        },
        { "type": "integer", "minimum": 0 }
      ]
    },
    "bandwidth_limits": {
      "type": "object",
      "properties": {
        "downstream": { "$ref": "#/definitions/byte_count" },
        "upstream": { "$ref": "#/definitions/byte_count" }
      },
      "additionalProperties": false,
      "required": [ "upstream", "downstream" ]
    },
    "storage": {
      "additionalProperties": false,
      "patternProperties": {
        "^.*$": {
          "type": "object",
          "properties": {
            "use_folder_tree": { "type": "boolean" },
            "limit": { "$ref": "#/definitions/byte_count" }
          },
          "additionalProperties": false,
          "required": [ "limit", "use_folder_tree" ]
        }
      },
      "type": "object",
      "minProperties": 1
    },
    "network": {
      "type": "object",
      "properties": {
        "bandwidth_limits": {
          "type": "object",
          "properties": {
            "month": { "$ref": "#/definitions/bandwidth_limits" },
            "sec": { "$ref": "#/definitions/bandwidth_limits" }
          },
          "additionalProperties": false,
          "required": [ "sec", "month" ]
        },
        "monitor": {
          "type": "object",
          "properties": {
            "enable_crawler": { "type": "boolean" },
            "enable_responses": { "type": "boolean" },
            "crawler_limit": { "type": "integer", "minimum": 0 },
            "crawler_interval": { "type": "integer", "minimum": 600 }
          },
          "additionalProperties": false,
          "required": [
            "enable_crawler",
            "enable_responses",
            "crawler_limit",
            "crawler_interval"
          ]
        },
        "port": {
          "oneOf": [
            { "type": "integer", "minimum": 1024, "maximum": 65535 },
            { "enum": [ "random" ] }
          ]
        },
        "bootstrap_nodes": {
          "type": "array",
          "items": {
            "type": "array",
            "items": [
              {"type": "string", "format": "ipv4"},
              {"type": "integer", "minimum": 1024, "maximum": 65535}
            ]
          }
        },
        "disable_data_transfer": { "type": "boolean" },
        "refresh_neighbours_interval": { "type": "integer", "minimum": 0}
      },
      "additionalProperties": false,
      "required": [
        "bandwidth_limits",
        "port",
        "bootstrap_nodes",
        "monitor",
        "disable_data_transfer",
        "refresh_neighbours_interval"
      ]
    }
  },

  "type": "object",
  "properties": {
    "version": { "type": "integer", "minimum": 0 },
    "storage": { "$ref": "#/definitions/storage" },
    "network": { "$ref": "#/definitions/network" },
    "cold_storage": {
      "type": "array",
      "items": {
        "pattern": "^[13][a-km-zA-HJ-NP-Z0-9]{26,33}$",
        "type": "string"
      }
    }
  },
  "required": [ "version", "cold_storage", "network", "storage" ],
  "additionalProperties": false
}
""")
