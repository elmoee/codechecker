#
# -------------------------------------------------------------------------
#
#  Part of the CodeChecker project, under the Apache License v2.0 with
#  LLVM Exceptions. See LICENSE for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
# -------------------------------------------------------------------------
""" CTU function test."""


import subprocess
import glob
import os
import shutil
import unittest

from subprocess import run
from typing import IO

from libtest import env
from libtest.codechecker import call_command, is_ctu_capable, \
    is_ctu_on_demand_capable
from libtest.ctu_decorators import makeSkipUnlessCTUCapable, \
    makeSkipUnlessCTUOnDemandCapable

CTU_ATTR = 'ctu_capable'
ON_DEMAND_ATTR = 'ctu_on_demand_capable'

skipUnlessCTUCapable = makeSkipUnlessCTUCapable(attribute=CTU_ATTR)
skipUnlessCTUOnDemandCapable = \
    makeSkipUnlessCTUOnDemandCapable(attribute=ON_DEMAND_ATTR)


class TestCtu(unittest.TestCase):
    """ Test CTU functionality. """

    def setup_class(self):
        """Setup the environment for testing ctu."""

        global TEST_WORKSPACE
        TEST_WORKSPACE = env.get_workspace('ctu')

        # Set the TEST_WORKSPACE used by the tests.
        os.environ['TEST_WORKSPACE'] = TEST_WORKSPACE

    def teardown_class(self):
        """Delete workspace."""

        # TODO: If environment variable is set keep the workspace
        # and print out the path.
        global TEST_WORKSPACE

        print('Removing: ' + TEST_WORKSPACE)
        shutil.rmtree(TEST_WORKSPACE)

    def setup_method(self, method):
        """ Set up workspace."""
        self.setUpWith('test_files_c', 'buildlog.json', 'reports_c')

    def setUpWith(self, input_dir, buildlog_json, report_dir):
        """
        Set up workspace with a given parameters. If called multiple times,
        teardown_method() must be called before this function.
        """
        # TEST_WORKSPACE is automatically set by test package __init__.py .
        self.test_workspace = os.environ['TEST_WORKSPACE']

        test_class = self.__class__.__name__
        print('Running ' + test_class + ' tests in ' + self.test_workspace)

        # Get the CodeChecker cmd if needed for the tests.
        self._codechecker_cmd = env.codechecker_cmd()
        self.env = env.codechecker_env()
        self.report_dir = os.path.join(self.test_workspace, report_dir)
        os.makedirs(self.report_dir)
        self.test_dir = os.path.join(os.path.dirname(__file__), input_dir)

        # Get if clang is CTU-capable or not.
        cmd = [self._codechecker_cmd, 'analyze', '-h']
        output, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 0, "Analyzing failed.")
        setattr(self, CTU_ATTR, is_ctu_capable(output))
        print("'analyze' reported CTU-compatibility? " +
              str(getattr(self, CTU_ATTR)))

        setattr(self, ON_DEMAND_ATTR, is_ctu_on_demand_capable(output))
        print("'analyze' reported CTU-on-demand-compatibility? " +
              str(getattr(self, ON_DEMAND_ATTR)))

        self.buildlog = os.path.join(self.test_workspace, buildlog_json)

        # Fix the "template" build JSONs to contain a proper directory.
        env.adjust_buildlog(
            buildlog_json, self.test_dir, self.test_workspace)

        self.__old_pwd = os.getcwd()
        os.chdir(self.test_workspace)

    def teardown_method(self, method):
        """ Tear down workspace."""

        shutil.rmtree(self.report_dir, ignore_errors=True)
        os.chdir(self.__old_pwd)

    @skipUnlessCTUCapable
    def test_ctu_loading_mode_requires_ctu_mode(self):
        """ Test ctu-ast-mode option requires ctu mode enabled. """
        cmd = [self._codechecker_cmd, 'analyze', '-o', self.report_dir,
               '--analyzers', 'clangsa', '--ctu-ast-mode=load-from-pch',
               self.buildlog]

        self.assertEqual(1,
                         run(cmd, cwd=self.test_dir, env=self.env).returncode)

    @skipUnlessCTUCapable
    def test_system_headers_last(self):
        """
        Test if implicit system include paths are appended after all
        user-defined flags and include paths in the pre-ctu phase.

        The build command in compilation_database.json is extended by the
        implicit include paths that are queried from the host compiler, since
        during analysis clang doesn't have these in case of a custom gcc host
        compiler. These implicit paths should always be appended to the end of
        the analyzer command otherwise the user's explicit include paths must
        take precedence. FYI: Compilers include a header file from the first(!)
        directory given by -I, -isystem, etc. flags where it is found.
        """
        cmd = [self._codechecker_cmd, 'analyze', '-o', self.report_dir,
               '--analyzers', 'clangsa', '--ctu', self.buildlog,
               '--verbose', 'debug']
        out = run(
            cmd, cwd=self.test_dir, env=self.env,
            stdout=subprocess.PIPE).stdout.decode()
        ast_cmd = next(filter(
            lambda line: 'Generating AST using' in line, out.splitlines()))

        self.assertLess(
            ast_cmd.index('non_existing'),
            ast_cmd.index('/usr/include'))

    @skipUnlessCTUCapable
    def test_ctu_all_ast_dump_based(self):
        """ Test full CTU AST-dump based analysis. """

        self.__test_ctu_all(on_demand=False)

    @skipUnlessCTUCapable
    @skipUnlessCTUOnDemandCapable
    def test_ctu_all_on_demand_parsed(self):
        """ Test full CTU on-demand-parsed ASTs. """

        self.__test_ctu_all(on_demand=True)

    @skipUnlessCTUCapable
    def test_ctu_collect_ast_dump_based(self):
        """ Test CTU collect phase with AST-dump based analysis. """

        self.__test_ctu_collect(on_demand=False)

    @skipUnlessCTUCapable
    @skipUnlessCTUOnDemandCapable
    def test_ctu_collect_on_demand_parsed(self):
        """
        Test CTU collect phase with on-demand-parsed AST based analysis.
        """

        self.__test_ctu_collect(on_demand=True)

    @skipUnlessCTUCapable
    def test_ctu_analyze_ast_dump_based_cpp(self):
        """ Test CTU analyze phase with AST-dump based analysis. """

        self.__test_ctu_analyze_cpp(on_demand=False)

    @skipUnlessCTUCapable
    @skipUnlessCTUOnDemandCapable
    def test_ctu_analyze_on_demand_parsed_cpp(self):
        """
        Test CTU analyze phase with on-demand-parsed AST based analysis.
        """

        self.__test_ctu_analyze_cpp(on_demand=True)

    @skipUnlessCTUCapable
    def test_ctu_analyze_ast_dump_based(self):
        """ Test CTU analyze phase with AST-dump based analysis. """

        self.__test_ctu_analyze(on_demand=False)

    @skipUnlessCTUCapable
    @skipUnlessCTUOnDemandCapable
    def test_ctu_analyze_on_demand_parsed(self):
        """
        Test CTU analyze phase with on-demand-parsed AST based analysis.
        """

        self.__test_ctu_analyze(on_demand=True)

    def __test_ctu_all(self, on_demand=False):
        """ Test full CTU. """

        output = self.__do_ctu_all(on_demand=on_demand)
        self.__check_ctu_analyze(output)

    def __test_ctu_collect(self, on_demand=False):
        """ Test CTU collect phase. """

        self.__do_ctu_collect(on_demand=on_demand)
        self.__check_ctu_collect(on_demand=on_demand)

    def __test_ctu_analyze(self, on_demand=False):
        """ Test CTU analyze phase. """

        self.__do_ctu_collect(on_demand=on_demand)
        output = self.__do_ctu_analyze(on_demand=on_demand)
        self.__check_ctu_analyze(output)

    def __test_ctu_analyze_cpp(self, on_demand=False):
        """ Test CTU analyze phase. """

        self.teardown_method(self.__test_ctu_analyze_cpp)
        self.setUpWith('test_files_cpp', 'buildlog.json', 'reports_cpp')

        self.__do_ctu_collect(on_demand=on_demand)
        # We specifically check whether spaces in the external function map
        # file work properly. The format of the file changed in between
        # clang-15 and clang-16, and this call checks whether clang is new
        # enough.
        if not self.__is_externalFnDef_in_new_format(on_demand=on_demand):
            return
        output = self.__do_ctu_analyze(on_demand=on_demand)
        self.__check_ctu_analyze_cpp(output)

    def __do_ctu_all(self, on_demand):
        """ Execute a full CTU run. """

        cmd = [self._codechecker_cmd, 'analyze', '-o', self.report_dir,
               '--analyzers', 'clangsa', '--ctu-all']

        if getattr(self, ON_DEMAND_ATTR):
            cmd.extend(['--ctu-ast-mode',
                        'parse-on-demand' if on_demand else 'load-from-pch'])

        cmd.append(self.buildlog)
        out, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 0, "Analyzing failed.")
        return out

    def __do_ctu_collect(self, on_demand):
        """ Execute CTU collect phase. """

        cmd = [self._codechecker_cmd, 'analyze', '-o', self.report_dir,
               '--analyzers', 'clangsa', '--ctu-collect']

        if getattr(self, ON_DEMAND_ATTR):
            cmd.extend(['--ctu-ast-mode',
                        'parse-on-demand' if on_demand else 'load-from-pch'])

        cmd.append(self.buildlog)
        _, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 0, "Analyzing failed.")

    def __check_ctu_collect(self, on_demand):
        """ Check artifacts of CTU collect phase. """

        ctu_dir = os.path.join(self.report_dir, 'ctu-dir')
        self.assertTrue(os.path.isdir(ctu_dir))
        for arch in glob.glob(os.path.join(ctu_dir, '*')):
            old_map_file = os.path.join(ctu_dir, arch, 'externalFnMap.txt')
            new_map_file = os.path.join(ctu_dir, arch, 'externalDefMap.txt')
            self.assertTrue(any(os.path.isfile(mapfile) for mapfile in
                                [old_map_file, new_map_file]))
            if not on_demand:
                ast_dir = os.path.join(ctu_dir, arch, 'ast')
                self.assertTrue(os.path.isdir(ast_dir))

    def __is_externalFnDef_in_new_format(self, on_demand):
        """
        The format of the external function map file changed in between
        clang-15 and clang-16, check whether this is the updated format.
        """

        ctu_dir = os.path.join(self.report_dir, 'ctu-dir')
        self.assertTrue(os.path.isdir(ctu_dir))
        for arch in glob.glob(os.path.join(ctu_dir, '*')):
            new_map_file = os.path.join(ctu_dir, arch, 'externalDefMap.txt')

            try:
                fn = open(new_map_file, "r")
                line = fn.readline()
                return line[0].isdigit()
            except IOError:
                print("Error: File does not appear to exist.")

    def __do_ctu_analyze(self, on_demand):
        """ Execute CTU analyze phase. """

        cmd = [self._codechecker_cmd, 'analyze', '-o', self.report_dir,
               '--analyzers', 'clangsa', '--ctu-analyze']

        if getattr(self, ON_DEMAND_ATTR):
            cmd.extend(['--ctu-ast-mode',
                        'parse-on-demand' if on_demand else 'load-from-pch'])

        cmd.append(self.buildlog)
        out, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 0, "Analyzing failed.")
        return out

    def __check_ctu_analyze(self, output):
        """ Check artifacts of CTU analyze phase. """

        self.assertNotIn("Failed to analyze", output)
        self.assertIn("analyzed lib.c successfully", output)
        self.assertIn("analyzed main.c successfully", output)

        cmd = [self._codechecker_cmd, 'parse', self.report_dir]
        output, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 2,
                         "Parsing could not found the expected bug.")
        self.assertIn("defect(s) in lib.c", output)
        self.assertIn("no defects in main.c", output)
        self.assertIn("lib.c:3:", output)
        self.assertIn("[core.NullDereference]", output)

        # We assume that only main.c has been analyzed with CTU and it involves
        # lib.c during its analysis.
        connections_dir = os.path.join(self.report_dir, 'ctu_connections')
        connections_files = os.listdir(connections_dir)
        self.assertEqual(len(connections_files), 1)

        connections_file = connections_files[0]
        self.assertTrue(connections_file.startswith('main.c'))

        with open(os.path.join(connections_dir, connections_file)) as f:
            self.assertTrue(f.readline().endswith('lib.c'))

    def __check_ctu_analyze_cpp(self, output):
        """ Check artifacts of CTU analyze phase. """

        self.assertNotIn("Failed to analyze", output)
        self.assertIn("analyzed space_in_lookup_name.cpp successfully", output)
        self.assertIn("analyzed space_in_lookup_name_trigger.cpp "
                      "successfully", output)

        cmd = [self._codechecker_cmd, 'parse', self.report_dir]
        output, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 2,
                         "Parsing could not found the expected bug.")
        self.assertIn("defect(s) in space_in_lookup_name.cpp", output)
        self.assertIn("no defects in space_in_lookup_name_trigger.cpp",
                      output)
        self.assertIn("space_in_lookup_name.cpp:2:", output)
        self.assertIn("[core.DivideZero]", output)

    @skipUnlessCTUCapable
    def test_ctu_makefile_generation(self):
        """ Test makefile generation in CTU mode. """

        cmd = [self._codechecker_cmd, 'analyze', '-o', self.report_dir,
               '--analyzers', 'clangsa', '--ctu', '--makefile']
        cmd.append(self.buildlog)
        _, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 0, "Analyzing failed.")

        _, _, result = call_command(["make"], cwd=self.report_dir,
                                    env=self.env)
        self.assertEqual(result, 0, "Performing generated Makefile failed.")

        # Check the output.
        cmd = [self._codechecker_cmd, 'parse', self.report_dir]
        output, _, result = call_command(cmd, cwd=self.test_dir, env=self.env)
        self.assertEqual(result, 2,
                         "Parsing could not found the expected bug.")
        self.assertIn("defect(s) in lib.c", output)
        self.assertIn("lib.c:3:", output)
        self.assertIn("[core.NullDereference]", output)

    @skipUnlessCTUCapable
    @skipUnlessCTUOnDemandCapable
    def test_ctu_ondemand_yaml_format(self):
        """ Test the generated YAML used in CTU on-demand mode.
        The YAML file should not contain newlines in individual entries in the
        generated textual format. """

        self.teardown_method(self.test_ctu_ondemand_yaml_format)
        self.setUpWith('test_files_c', 'complex_buildlog.json', 'reports_c')

        # Copy test files to a directory which file path will be longer than
        # 128 chars to test the yaml parser.
        test_dir = os.path.join(
            self.test_workspace, os.path.join(*[
                ''.join('0' for _ in range(43)) for _ in range(0, 3)]))

        shutil.copytree(self.test_dir, test_dir)

        complex_buildlog = os.path.join(test_dir, 'complex_buildlog.json')
        shutil.copy(self.buildlog, complex_buildlog)
        env.adjust_buildlog('complex_buildlog.json', test_dir, test_dir)

        cmd = [self._codechecker_cmd, 'analyze',
               '-o', self.report_dir,
               '--analyzers', 'clangsa',
               '--ctu-collect',  # ctu-directory is needed, and it remains
                                 # intact only if a single ctu-phase is
                                 # specified
               '--ctu-ast-mode', 'parse-on-demand',
               complex_buildlog]
        _, _, result = call_command(cmd, cwd=test_dir, env=self.env)
        self.assertEqual(result, 0, "Analyzing failed.")

        ctu_dir = os.path.join(self.report_dir, 'ctu-dir')

        # In order to be architecture-invariant, ctu directory is searched for
        # invocation list files.
        invocation_list_paths = list(glob.glob(
            os.path.join(ctu_dir, '*', 'invocation-list.yml')))

        # At least one invocation list should exist.
        self.assertGreaterEqual(len(invocation_list_paths), 1)

        # Assert that every line begins with either - or / to approximate that
        # the line is not a line-broken list entry. If there is no newline in
        # the textual representation, then every line either starts with a /
        # (if it is an absolute path posing as a key) or - (if it is a list
        # entry). This requirement of format is a workaround for the LLVM YAML
        # parser.
        def assert_no_linebreak(invocation_list_file: IO):
            invocation_lines = invocation_list_file.readlines()
            for line in invocation_lines:
                self.assertRegex(line, '^ *[-/]')

        for invocation_list_path in invocation_list_paths:
            with open(invocation_list_path) as invocation_list_file:
                assert_no_linebreak(invocation_list_file)
