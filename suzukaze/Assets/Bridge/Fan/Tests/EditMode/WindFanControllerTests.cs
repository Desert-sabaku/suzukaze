using System;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Suzukaze.Fan.Tests
{
    public class WindFanControllerTests
    {
        // Default layout: 0, 60, 120, 180, -120 and -60 degrees, 1.5 apart from the player.
        private const int Front = 0;
        private const int FrontRight = 1;
        private const int BackRight = 2;
        private const int Back = 3;
        private const int BackLeft = 4;
        private const int FrontLeft = 5;

        private WindFanController controller;
        private Transform playerCamera;

        [SetUp]
        public void SetUp()
        {
            controller = new GameObject("WindFanController").AddComponent<WindFanController>();
            playerCamera = new GameObject("PlayerCamera").transform;
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(playerCamera.gameObject);
            Object.DestroyImmediate(controller.gameObject);
        }

        [Test]
        public void WindTravellingForwardComesFromTheFanBehind()
        {
            byte[] output = controller.CalculateFanPower(playerCamera, Vector3.forward, 1f);
            Assert.AreEqual(WindFanController.FanCount, output.Length);
            Assert.AreEqual(255, output[Back]);
            Assert.AreEqual(0, output[Front]);
            Assert.AreEqual(0, output[FrontRight]);
            Assert.AreEqual(0, output[FrontLeft]);
            // cos 60° = 0.5 for both rear-side fans.
            Assert.AreEqual(output[BackRight], output[BackLeft]);
            Assert.That(output[BackRight], Is.InRange(127, 128));
        }

        [Test]
        public void ZeroWindTurnsEveryFanOff() =>
            CollectionAssert.AreEqual(new byte[6], controller.CalculateFanPower(playerCamera, Vector3.zero, 1f));

        [Test]
        public void VerticalWindTurnsEveryFanOff() =>
            CollectionAssert.AreEqual(new byte[6], controller.CalculateFanPower(playerCamera, Vector3.up, 1f));

        [Test]
        public void OnlyTheDirectionOfTheWindMatters() =>
            CollectionAssert.AreEqual(
                controller.CalculateFanPower(playerCamera, Vector3.right, 1f),
                controller.CalculateFanPower(playerCamera, Vector3.right * 5f, 1f));

        [TestCase(0f, 0)]
        [TestCase(0.2f, 51)]
        [TestCase(1f, 255)]
        [TestCase(2f, 255)]
        [TestCase(-1f, 0)]
        public void PowerScalesTheOutput(float power, int expected) =>
            Assert.AreEqual(expected, controller.CalculateFanPower(playerCamera, Vector3.forward, power)[Back]);

        [Test]
        public void FansTurnWithTheCameraHeading()
        {
            playerCamera.SetPositionAndRotation(new Vector3(1f, 2f, 3f), Quaternion.Euler(0f, 90f, 0f));
            AssertNear(new Vector3(2.5f, 2f, 3f), controller.GetFanPosition(playerCamera, Front));
            AssertNear(new Vector3(-0.5f, 2f, 3f), controller.GetFanPosition(playerCamera, Back));
            Assert.AreEqual(255, controller.CalculateFanPower(playerCamera, Vector3.forward, 1f)[Back]);
        }

        [TestCase(60f)]
        [TestCase(90f)]
        [TestCase(-90f)]
        public void FansStayLevelWhenTheCameraPitches(float pitch)
        {
            playerCamera.rotation = Quaternion.Euler(pitch, 0f, 0f);
            AssertNear(new Vector3(0f, 0f, 1.5f), controller.GetFanPosition(playerCamera, Front));
        }

        [Test]
        public void OnlyTheLevelPartOfTheWindReachesTheFans()
        {
            // Camera forward points 30° below the horizon, so cos 30° of it is level.
            playerCamera.rotation = Quaternion.Euler(30f, 0f, 0f);
            Assert.AreEqual(221, controller.CalculateFanPower(playerCamera, Vector3.forward, 1f)[Back]);
        }

        [Test]
        public void MissingCameraIsRejected() =>
            Assert.Throws<ArgumentNullException>(() => controller.CalculateFanPower(null, Vector3.forward, 1f));

        [Test]
        public void TestResultChangesOnlyWhenApplied()
        {
            var serialized = new SerializedObject(controller);
            serialized.FindProperty("referenceCamera").objectReferenceValue = playerCamera;
            serialized.FindProperty("testWindDirection").vector3Value = Vector3.back;
            serialized.FindProperty("testWindPower").floatValue = 1f;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            controller.ApplyTestWind();
            serialized.Update();
            Assert.AreEqual(255, TestResult(serialized, Front));

            serialized.FindProperty("testWindDirection").vector3Value = Vector3.forward;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            serialized.Update();
            Assert.AreEqual(255, TestResult(serialized, Front));

            controller.ApplyTestWind();
            serialized.Update();
            Assert.AreEqual(0, TestResult(serialized, Front));
            Assert.AreEqual(255, TestResult(serialized, Back));
        }

        [Test]
        public void StopTestWindClearsTheResult()
        {
            controller.ReferenceCamera = playerCamera;
            controller.ApplyTestWind();
            controller.StopTestWind();
            var serialized = new SerializedObject(controller);
            for (int fan = 0; fan < WindFanController.FanCount; fan++)
                Assert.AreEqual(0, TestResult(serialized, fan));
            Assert.AreEqual(0f, serialized.FindProperty("appliedTestWindPower").floatValue);
        }

        private static int TestResult(SerializedObject serialized, int fan) =>
            serialized.FindProperty("testResult").GetArrayElementAtIndex(fan).intValue;

        private static void AssertNear(Vector3 expected, Vector3 actual) =>
            Assert.That(Vector3.Distance(expected, actual), Is.LessThan(1e-4f), $"expected {expected}, got {actual}");
    }
}
