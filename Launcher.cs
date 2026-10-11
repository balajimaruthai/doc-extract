using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace DocExtract
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string logFile = Path.Combine(baseDir, "launcher.log");
            try
            {
                string scriptPath = Path.Combine(baseDir, "app_desktop.pyw");
                string pythonw = @"C:\Users\Zynee\anaconda3\pythonw.exe";
                if (!File.Exists(pythonw))
                {
                    pythonw = "pythonw.exe";
                }

                File.WriteAllText(logFile, "Launching: " + pythonw + " " + scriptPath + "\n");

                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = pythonw;
                psi.Arguments = string.Format("\"{0}\"", scriptPath);
                psi.WorkingDirectory = baseDir;
                psi.UseShellExecute = true;
                psi.WindowStyle = ProcessWindowStyle.Hidden;


                Process p = Process.Start(psi);
                File.AppendAllText(logFile, "Spawned PID: " + (p != null ? p.Id.ToString() : "null") + "\n");
            }
            catch (Exception ex)
            {
                File.AppendAllText(logFile, "Error: " + ex.ToString() + "\n");
                MessageBox.Show("Failed to launch DocExtract:\n" + ex.Message, "DocExtract", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
