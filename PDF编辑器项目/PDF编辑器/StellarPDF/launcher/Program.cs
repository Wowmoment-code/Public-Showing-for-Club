using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class Program
{
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [STAThread]
    private static void Main(string[] args)
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string projectDir = Path.Combine(baseDir, "StellarPDF");
        string appPath = Path.Combine(projectDir, "bin", "星澜PDF_主程序.exe");

        if (!File.Exists(appPath))
        {
            MessageBox.Show(
                "找不到主程序：\n" + appPath + "\n\n请确保 StellarPDF 文件夹与启动器放在同一目录。",
                "星澜 PDF",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        string temp = Path.Combine(projectDir, "runtime", "temp");
        try
        {
            Directory.CreateDirectory(temp);
        }
        catch
        {
            try
            {
                temp = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "StellarPDF", "temp");
                Directory.CreateDirectory(temp);
            }
            catch
            {
                temp = Path.GetTempPath();
            }
        }

        try
        {
            ProcessStartInfo info = new ProcessStartInfo(appPath);
            info.WorkingDirectory = Path.GetDirectoryName(appPath);
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables["TEMP"] = temp;
            info.EnvironmentVariables["TMP"] = temp;
            info.EnvironmentVariables["STELLAR_DATA_DIR"] = Path.Combine(projectDir, "bin", "StellarPDF", "runtime");
            if (args != null && args.Length > 0)
            {
                StringBuilder commandLine = new StringBuilder();
                foreach (string arg in args)
                {
                    if (commandLine.Length > 0) commandLine.Append(' ');
                    commandLine.Append('"').Append(arg.Replace("\"", "\\\"")).Append('"');
                }
                info.Arguments = commandLine.ToString();
            }
            Process process = Process.Start(info);
            // Make sure the editor comes to the foreground even when the
            // launcher was started by Explorer or a file association.
            if (process != null)
            {
                try
                {
                    process.WaitForInputIdle(8000);
                    for (int i = 0; i < 80; i++)
                    {
                        process.Refresh();
                        if (process.MainWindowHandle != IntPtr.Zero) break;
                        Thread.Sleep(100);
                    }
                    process.Refresh();
                    IntPtr handle = process.MainWindowHandle;
                    if (handle != IntPtr.Zero)
                    {
                        ShowWindow(handle, 5); // SW_SHOW - keep maximized state
                        SetForegroundWindow(handle);
                    }
                }
                catch
                {
                }
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "启动星澜 PDF 失败：\n" + ex.Message,
                "星澜 PDF",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }
}
