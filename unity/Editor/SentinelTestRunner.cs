// UNITY SENTINEL — Unity Test Framework result import.
//
// UNITY SENTINEL deliberately does not re-implement the Test Runner. Instead it
// imports the NUnit XML that the Unity Test Framework produces
// (Unity -batchmode -runTests -testPlatform EditMode -testResults results.xml)
// and turns it into a compact JSON summary that the Python report can consume.
//
// If the results file does not exist the runner reports NOT RUN — it never
// fabricates a test outcome.

using System;
using System.IO;
using System.Xml;
using UnityEngine;

namespace UnitySentinel.EditorTools
{
    /// <summary>Summary of an NUnit result file.</summary>
    [Serializable]
    public class SentinelTestSummary
    {
        public string sourceFile;
        public string status = "NOT RUN";
        public int total;
        public int passed;
        public int failed;
        public int skipped;
        public string message;
        public string[] failedTests = new string[0];
    }

    /// <summary>Parses Unity Test Framework result files.</summary>
    public static class SentinelTestRunner
    {
        private const string LogPrefix = "[Unity Sentinel]";

        /// <summary>Parse a NUnit3 XML result file produced by Unity.</summary>
        public static SentinelTestSummary ParseResults(string xmlPath)
        {
            var summary = new SentinelTestSummary { sourceFile = xmlPath };
            if (string.IsNullOrEmpty(xmlPath) || !File.Exists(xmlPath))
            {
                summary.status = "NOT RUN";
                summary.message = "Result file not found. Run Unity with -runTests to produce it.";
                return summary;
            }

            var failed = new System.Collections.Generic.List<string>();
            try
            {
                var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null };
                using (var reader = XmlReader.Create(xmlPath, settings))
                {
                    var document = new XmlDocument { XmlResolver = null };
                    document.Load(reader);

                    XmlElement run = document.DocumentElement;
                    if (run != null)
                    {
                        summary.total = ReadAttribute(run, "total");
                        summary.passed = ReadAttribute(run, "passed");
                        summary.failed = ReadAttribute(run, "failed");
                        summary.skipped = ReadAttribute(run, "skipped");
                    }

                    XmlNodeList failedNodes = document.SelectNodes("//test-case[@result='Failed']");
                    if (failedNodes != null)
                    {
                        foreach (XmlNode node in failedNodes)
                        {
                            if (node.Attributes != null && node.Attributes["name"] != null)
                            {
                                failed.Add(node.Attributes["name"].Value);
                            }
                        }
                    }
                }

                summary.failedTests = failed.ToArray();
                if (summary.failed > 0)
                {
                    summary.status = "FAIL";
                }
                else if (summary.total == 0)
                {
                    summary.status = "NOT VERIFIED";
                    summary.message = "Result file contains no test cases.";
                }
                else
                {
                    summary.status = "PASS";
                }
            }
            catch (Exception exception)
            {
                summary.status = "NOT VERIFIED";
                summary.message = "Result file could not be parsed: " + exception.Message;
            }

            return summary;
        }

        /// <summary>
        /// Parse results and write a JSON summary next to the project.
        /// When <paramref name="xmlPath"/> is empty the path is read from the
        /// <c>-sentinelResults</c> command line argument, so the method can be
        /// called from batchmode via <c>-executeMethod</c>.
        /// </summary>
        public static string ImportAndWrite(string xmlPath)
        {
            if (string.IsNullOrEmpty(xmlPath))
            {
                xmlPath = GetArgument("-sentinelResults");
            }

            SentinelTestSummary summary = ParseResults(xmlPath);
            string root = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
            string directory = Path.Combine(root, ".sentinel");
            Directory.CreateDirectory(directory);
            string output = Path.Combine(directory, "unity-test-results.json");
            File.WriteAllText(output, JsonUtility.ToJson(summary, true));
            Debug.Log(LogPrefix + " Test results imported: " + summary.status + " (" + output + ")");
            return output;
        }

        private static string GetArgument(string name)
        {
            string[] arguments = Environment.GetCommandLineArgs();
            for (int index = 0; index < arguments.Length - 1; index++)
            {
                if (arguments[index] == name)
                {
                    return arguments[index + 1];
                }
            }

            return null;
        }

        private static int ReadAttribute(XmlElement element, string name)
        {
            if (element.Attributes == null)
            {
                return 0;
            }

            XmlAttribute attribute = element.Attributes[name];
            if (attribute == null)
            {
                return 0;
            }

            int value;
            return int.TryParse(attribute.Value, out value) ? value : 0;
        }
    }
}
