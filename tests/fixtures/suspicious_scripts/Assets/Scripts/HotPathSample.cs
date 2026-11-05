using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;

public class HotPathSample : MonoBehaviour
{
    private void Update()
    {
        var target = FindObjectOfType<HotPathSample>();
        var rb = GetComponent<Rigidbody>();
        string label = "value: " + target + " at " + Time.time;
        var visible = FindObjectsOfType<HotPathSample>().Where(x => x != null).ToList();
        Debug.Log(label + visible.Count);
    }

    public void LoadConfig()
    {
        var text = File.ReadAllText("config.txt");
        Debug.Log(text);
    }
}
