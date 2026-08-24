import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.gui.test.TestThread;
import com.cburch.logisim.proj.Project;
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

/** Runs Logisim Evolution test vectors without creating a GUI window. */
public final class HeadlessLogisimTest {
  private static final class ConsoleLoader extends Loader {
    ConsoleLoader() {
      super(null);
    }

    @Override
    public void showError(String description) {
      System.err.println("LOGISIM LOAD WARNING: " + description);
    }
  }

  private HeadlessLogisimTest() {}

  public static void main(String[] args) throws Exception {
    if (args.length != 3) {
      throw new IllegalArgumentException("usage: project.circ circuit vectors.txt");
    }

    Loader loader = new ConsoleLoader();
    LogisimFile file;
    try (FileInputStream input = new FileInputStream(args[0])) {
      file = LogisimFile.load(input, loader);
    }
    Circuit circuit = file.getCircuit(args[1]);
    if (circuit == null) {
      throw new IllegalArgumentException("unknown circuit: " + args[1]);
    }

    Project project = new Project(file);
    project.setCurrentCircuit(circuit);

    PrintStream console = System.out;
    ByteArrayOutputStream captured = new ByteArrayOutputStream();
    int failures;
    try (PrintStream quiet = new PrintStream(captured, true, StandardCharsets.UTF_8)) {
      System.setOut(quiet);
      failures = TestThread.doTestVector(project, circuit, args[2]);
    } finally {
      System.setOut(console);
    }

    if (failures != 0) {
      System.err.print(captured.toString(StandardCharsets.UTF_8));
      System.exit(1);
    }
    System.out.printf("PASS %-20s %s%n", args[1], args[2]);
    // Logisim owns non-daemon AWT/executor threads even in headless mode.
    System.exit(0);
  }
}
