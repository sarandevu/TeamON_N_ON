fun probe(r: android.hardware.camera2.R<FloatArray>) {
    val arr: FloatArray = r.toFloatArray()
    println("OK: ${arr.size}")
}
fun main() {
    println("compiled")
}
