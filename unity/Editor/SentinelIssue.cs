// UNITY SENTINEL — shared Editor-side issue model.
// Belongs to the Editor assembly; never included in player builds.

using System;

namespace UnitySentinel.EditorTools
{
    /// <summary>A single problem reported by an Editor-side validator.</summary>
    [Serializable]
    public class SentinelIssue
    {
        public string code;
        public string severity;
        public string message;
        public string assetPath;
        public string objectPath;
        public string recommendation;

        public SentinelIssue()
        {
        }

        public SentinelIssue(string code, string severity, string message, string assetPath, string objectPath, string recommendation)
        {
            this.code = code;
            this.severity = severity;
            this.message = message;
            this.assetPath = assetPath;
            this.objectPath = objectPath;
            this.recommendation = recommendation;
        }

        public override string ToString()
        {
            return "[" + severity + "] " + code + " " + assetPath + " — " + message;
        }
    }

    /// <summary>Aggregated result of an Editor-side validation run.</summary>
    [Serializable]
    public class SentinelValidationReport
    {
        public string generatedAt;
        public string unityVersion;
        public string kind;
        public int assetCount;
        public int issueCount;
        public SentinelIssue[] issues = new SentinelIssue[0];
    }
}
